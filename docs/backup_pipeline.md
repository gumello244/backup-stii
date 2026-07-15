# Backup Lifecycle: Fetching, Processing, and Rendering Pipeline

This document describes how the Remos application discovers backup sources, processes them to resolve conflicts, and renders/restores the result.

---

## 1. High-Level Architecture

The backup pipeline operates in three main phases, followed by restoration:
1. **Fetching (Discovery)**: Scanning local drives and network locations in a background thread to find candidate backups.
2. **Processing (Merging & Selection)**: Walking directories in parallel, resolving paths, and extracting the newest source in normal mode or merging them in admin mode.
3. **Restoration (Copy & Conflict Resolution)**: Copying files in parallel, handling retry/backoffs, performing write elevation via helper process, skipping identical files, and exporting conflicts.
4. **Rendering (UI Presentation)**: Presenting status card summaries inside PyQt5 views.

```mermaid
graph TD
    subgraph 1. Fetching (Discovery)
        A[Start Discovery] --> B[detect_user_login & hostname]
        B --> C{Admin Mode / Custom Query?}
        C -- Yes --> D[Search stages / query match with Cache check]
        C -- No --> E[Scan network & local for user profile]
        D --> F[Build source list with cheap probes]
        E --> F
    end

    subgraph 2. Processing (Merging & Selection)
        F --> G[Process / Merge Sources]
        G --> H[Index files in parallel using ThreadPoolExecutor max 4]
        H --> I{Admin Mode?}
        I -- Yes --> J[Merge all sources: keep newest mtime]
        I -- No --> K[Filter: keep only the single source with newest file]
        J --> L[Filter Contacts exception & exclude system noise]
        K --> L
        L --> M[Generate MergedFileSet]
    end

    subgraph 3. Restoration (Copying)
        M --> N[CopyFilesWorker thread]
        N --> O[Check identical / check conflict]
        O --> P[Route to elevated helper if C:\\Users\\other]
        P --> Q[Copy in parallel: ThreadPoolExecutor max 4]
        Q --> R[Exponential backoff retries & circuit breaker]
        R --> S[End-of-Run retry phase]
    end
```

---

## 2. Fetching Phase (Backup Discovery)

Backup discovery is managed by the [backup_discovery.py](file:///c:/Users/100229/Documents/OC/Remos/services/backup_discovery.py) and [admin_backup_discovery.py](file:///c:/Users/100229/Documents/OC/Remos/services/admin_backup_discovery.py) services.

### User and Machine Identification
- **User Login**: Current Windows login name is dynamically detected via `detect_user_login()` using `os.environ.get("USERNAME", os.getlogin())`.
- **Machine ID**: Extracted from the hostname via `extract_machine_id()` matching patterns like `PMC_<digits>` or any 6-digit number.

### Mode Differentiation in Fetching
1. **Normal User Mode (`admin_mode = False`)**:
   - The engine targets backups strictly matching the logged-in user and current machine ID.
   - It scans the network share and local drives.
   - If directories match the machine ID, they are returned. Otherwise, it falls back to folders matching the login username.
   - Local scanning recurses non-system folders up to depth 2 looking for directories containing the user's login.
2. **Admin Mode (`admin_mode = True` / Custom Query)**:
   - When a `custom_query` is provided in the search bar, the discovery scans candidates *only* matching that query (folder name or profile names).
   - If no custom query is specified, it scans all network/local candidates in three progressive stages:
     - **Stage 1 (`machine`)**: Matches by machine ID from hostname.
     - **Stage 2 (`current_user`)**: Matches local user profiles, starting with the current user.
     - **Stage 3 (`machine_users`)**: Matches other users' profiles present on the machine.
   - **Flat Profile Matching**: Detects ad-hoc backups saved directly under the share (where user profile folders are nested one level down without a `RAIZ`/`USUARIOS` wrapper structure).

### Discovery Caching
- A thread-safe dictionary `_DISCOVERY_CACHE` is used to prevent redundant network scans during fast query inputs or stage transitions.
- The cache holds a timestamped candidate listing mapped by `(server_ip, share)`.
- If the time elapsed is less than `DISCOVERY_CACHE_TTL_SECONDS` (configured in `app_secrets.py`, defaults to 30.0s), cached directories are reused.
- The cache is automatically bypassed under unit/pytest test runners to ensure test isolation.

### Lazy Detail Evaluation
- Walking directory structures recursively to get size details is slow. Broad scans initially only perform a cheap check (`_has_any_file`) to prove a candidate has at least one restorable file.
- The exact statistics (`size_bytes`, `file_count`, `dir_count`) are left as `PENDING_STATS` (`-1`) during search.
- When the administrator selects a candidate in the UI, detailed file walk stats are computed asynchronously in a background worker `load_source_details` using a `ThreadPoolExecutor` (max 4 concurrent tasks).

### Root (`RAIZ`) Folder Detection
- In `_build_source()`, Remos checks for the existence of a `RAIZ` directory parallel to the user profile (i.e. `<backup_root>/RAIZ`).
- If found, its size is recursively counted and added to the source's `total_bytes`, and `"RAIZ"` is appended to the source's `folder_list` as a virtual directory.

---

## 3. Processing Phase (Backup Merger)

If backup sources are found, they are processed by the [backup_merger.py](file:///c:/Users/100229/Documents/OC/Remos/services/backup_merger.py) service inside a background `MergeSourcesWorker` thread.

### File Indexing
- For each `BackupSource`, `_index_source()` walks all directories.
- If a folder is named `"RAIZ"`, the indexing path is mapped directly to the parallel `<backup_root>/RAIZ` directory.
- Indexing is performed in parallel using a `ThreadPoolExecutor` with a thread limit of `MAX_CONCURRENT_DISCOVERY_TASKS = 4` (defined in [config.py](file:///c:/Users/100229/Documents/OC/Remos/config.py)) to avoid network congestion.
- Files are registered in an index dictionary using `(dest_folder, relative_name)` as the unique key.

### File Skipping and Filtering
During indexing and merge preprocessing, the following items are filtered:
1. **System Files**: Files named `desktop.ini`, `thumbs.db`, and `.ds_store` are completely excluded.
2. **Contacts Folder Exception**: If a `Contacts` folder contains only one file (which is common for empty system profiles containing a placeholder card), it is ignored to prevent restoring useless files.

### Resolution Strategy (Conflict Resolution)
Depending on the application's active mode, Remos resolves the sources using one of two strategies:
1. **Normal User Mode (`admin_mode = False`)**:
   - Remos performs a winner-take-all filtering: it finds the single backup source containing the newest file modification time (`mtime`) in its index.
   - It selects only this source, discarding all other sources. No cross-source merging is performed.
2. **Admin Mode (`admin_mode = True`)**:
   - Remos merges all sources together.
   - If a file is present in multiple sources, Remos compares their modification times (`mtime`) and keeps the version with the most recent timestamp.

---

## 4. Restoration Phase (Backup Copier)

Restoration is managed by the [backup_copier.py](file:///c:/Users/100229/Documents/OC/Remos/services/backup_copier.py) service and orchestrated by `CopyFilesWorker` in the background.

### Copy Concurrency
- Copying is executed over a thread pool via a `ThreadPoolExecutor` with `COPY_WORKERS = 4` (defined in [config.py](file:///c:/Users/100229/Documents/OC/Remos/config.py)).
- Concurrency hides per-file overhead (such as remote filesystem syscalls and UAC pipe IPC round-trips), which dominates when handling thousands of small files.

### File Ordering & Prioritization
- **No Priority Sort**: There is no custom sorting (e.g., sorting by size or date) applied to the restoration list before copying.
- **Natural Order**: Files are copied in the order they were compiled during merging (generally alphabetical by directory name, followed by `RAIZ`).
- **Parallel Completion**: Due to the thread pool execution, smaller files naturally finish faster.
- **End-of-Run Retry**: The only ordered transition is that failed files are deferred and retried sequentially at the very end of the run.

### Destination Checking (Skip & Conflict Logic)
Before copying a file, the copier resolves the destination path and applies checking rules:
- **Identical Files**: If a file already exists at the destination with matching size and modification time (within a 2-second tolerance), it is silently skipped. In cut mode, the source file is deleted.
- **Conflict Files**: If the destination file exists but has a different size or modification time, it is classified as a conflict. It is logged in `skipped_files` as `"já existia no destino com conteúdo diferente"` and skipped, ensuring existing user files are never overwritten.
- **No Conflict**: If the destination file does not exist, the copy proceeds.

### Sleep Prevention
- During copy operations, Windows sleep is prevented via kernel32's `SetThreadExecutionState` using continuous system-required flags. This flag is cleared when copying completes.

### Write Elevation
- If a destination path sits in another Windows user's profile under `C:\Users\`, writing directly raises a `PermissionError`.
- If this process does not already hold an admin token, the write is routed through an elevated helper process (`services/elevation.py`) using named pipes. This prompts a single UAC challenge upon start.

### Cut Mode
- In cut mode (moving files), Remos tries to perform a metadata-only rename (`os.rename`) on the local disk (typically `<1ms`).
- If the rename fails (e.g. cross-device move), it falls back to a chunk-by-chunk copy and deletes the source file afterwards.

### Resilience, Circuit Breaking, and Retries
- **Exponential Backoff**: Transient errors (e.g., brief network drop) are retried per file with exponential backoff: `backoff_base * (2 ** attempt)`.
- **Circuit Breaker**: If consecutive failures reach `consecutive_fail_limit` (defaults to 3), the copy loop aborts. Remaining files are marked as failed with the reason `"Não processado — operação interrompida após falhas consecutivas"`.
- **Deferred Final Retry**: Files that failed during parallel execution are retried one final time sequentially at the end of the run.
- **Exporting Conflicts**: After completion, a prompt allows exporting all skipped/conflict files to a dedicated folder on the user's desktop (`Remos - Arquivos Pulados`) for manual inspection.

---

## 5. Rendering Phase (Bento Grid layout)

Once processing completes, the result is displayed inside [AnalysisView](file:///c:/Users/100229/Documents/OC/Remos/ui/views/analysis_view.py) via a centered Bento Grid.

### Card Layout
The Bento Grid displays two cards stacked vertically:
1. **Hero Card**:
   - In user mode, it shows `"ARQUIVOS SALVOS EM"` with the date of the newest file in the backup set (formatted as `DD/MM/YYYY`).
   - In admin mode, it shows `"FONTE"` with the source summary describing the origins of the merged backups.
   - It is styled with a light blue background, constrained to a fixed size of `320x100px`, and its contents are centered.
2. **"ENCONTRADOS" Card**:
   - Displays the count of unique files found and the number of distinct folders (e.g. `"15 arquivos"`, `"Em 2 pastas"`).
   - Stacks directly below the Hero Card.
   - It is styled with a soft gray background, set to a fixed width of `320px`, and its contents are centered.
