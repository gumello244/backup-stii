# Backup Lifecycle: Fetching, Processing, and Rendering Pipeline

This document describes how the Remos application discovers backup sources, processes them to resolve conflicts, and renders the result in a Bento Grid layout.

---

## 1. High-Level Architecture

The backup pipeline operates in three distinct phases:
1. **Fetching (Discovery)**: Scanning local drives and network locations in a background thread to find candidate backups for the logged-in user.
2. **Processing (Merging & Selection)**: Walking files in parallel, resolving paths, and extracting the newest source in normal mode or merging them in admin mode.
3. **Rendering (UI Presentation)**: Presenting the selected or merged metrics via centered, stacked Bento cards inside a PyQt5 layout.

```mermaid
graph TD
    subgraph 1. Fetching (Discovery)
        A[Start Discovery] --> B[detect_user_login & hostname]
        B --> C[Scan Network Source]
        B --> D[Scan All Local Drives]
        C --> E[Filter by Machine ID / Login]
        D --> F[Find matches on C, D, etc. excluding system dirs]
        E --> G[Collect BackupSource list & include RAIZ folders]
        F --> G
    end

    subgraph 2. Processing (Merging & Selection)
        G --> H[Process / Merge Sources]
        H --> I[Index files in parallel using ThreadPoolExecutor max 4]
        I --> J{Admin Mode?}
        J -- Yes --> K[Merge all sources: keep newest mtime]
        J -- No --> L[Filter: keep only the single source with newest file]
        K --> M[Group by destination folder & calculate totals]
        L --> M
        M --> N[Generate MergedFileSet]
    end

    subgraph 3. Rendering (UI Presentation)
        N --> O[MainWindow Central Stack]
        O --> P[Render BentoGrid stacked vertically]
        P --> Q[Hero Card: ARQUIVOS SALVOS EM / FONTE centered 320x100px]
        P --> R[ENCONTRADOS Card: File & Folder counts centered 320px width]
    end
```

---

## 2. Fetching Phase (Backup Discovery)

Backup discovery is managed by the [backup_discovery.py](file:///c:/Users/100229/Documents/OC/Remos/services/backup_discovery.py) service and orchestrated by `DiscoverSourcesWorker` in the background.

### User and Machine Identification
- **User Login**: Current Windows login name is dynamically detected via `detect_user_login()` using `os.environ.get("USERNAME", os.getlogin())`.
- **Machine ID**: Extracted from the hostname via `extract_machine_id()` matching patterns like `PMC_<digits>` or any 6-digit number.

### Scanning Network Location
- Looks at the network path `\\<server_ip>\<share>`.
- Searches for subfolders matching the user login and prioritizes those matching the machine's ID.
- Sorts directories by modification time and returns the newest matches (or all matches if `admin_mode` is enabled).

### Scanning Local Drives
- Dynamically queries all active Windows drive letters (`A:\` to `Z:\`) using `get_local_drives()`.
- Walks each active drive, excluding common system directories to maximize speed (e.g., `Windows`, `Program Files`, `Users`, `Temp`).
- Recursively searches non-system folders up to depth 2 for directories containing the user's login.

### Root (`RAIZ`) Folder Detection
- In `_build_source()`, Remos checks for the existence of a `RAIZ` directory parallel to the user profile (i.e. `<backup_root>/RAIZ`).
- If found, its size is recursively counted and added to the source's `total_bytes`, and `"RAIZ"` is appended to the source's `folder_list` as a virtual directory.

---

## 3. Processing Phase (Backup Merger)

If backup sources are found, they are processed by the [backup_merger.py](file:///c:/Users/100229/Documents/OC/Remos/services/backup_merger.py) service inside a background `MergeSourcesWorker` thread.

### File Indexing
- For each `BackupSource`, `_index_source()` walks all directories.
- Standard system files (e.g., `desktop.ini`, `thumbs.db`, `.ds_store`) are excluded from the index.
- If a folder is named `"RAIZ"`, the indexing path is mapped directly to the parallel `<backup_root>/RAIZ` directory.
- Indexing is performed in parallel using a `ThreadPoolExecutor` with a thread limit of `MAX_CONCURRENT_DISCOVERY_TASKS = 4` (defined in [config.py](file:///c:/Users/100229/Documents/OC/Remos/config.py)) to avoid network overwhelming.
- Files are registered in an internal dictionary using the destination folder and relative path as the unique key: `(dest_folder, relative_name)`.

### Resolution Strategy
Depending on the application's active mode, Remos resolves the sources using one of two strategies:
1. **Normal User Mode (`admin_mode = False`)**:
   - Remos iterates through the files in all discovered source indexes to find the backup source containing the single most recent file modification time.
   - It selects only this source, discarding all other sources and their file indexes. No merging or cross-source conflict resolution is performed.
2. **Admin Mode (`admin_mode = True`)**:
   - Remos merges all sources together.
   - For files present in multiple sources, Remos compares their modification times (`mtime`) and keeps the version with the most recent timestamp.

### Grouping and Results
- The selected or merged files are grouped by destination folder (`group_by_folder()`) to calculate the count of files and consolidated byte size.
- A `MergedFileSet` object is generated containing the list of files, folder summaries, total size, and a source origin summary (e.g. `"Rede"`, `"Local"`, or `"Mesclado (rede + local)"`).

---

## 4. Rendering Phase (Bento Grid layout)

Once processing completes, the result is displayed inside [AnalysisView](file:///c:/Users/100229/Documents/OC/Remos/ui/views/analysis_view.py) via a centered Bento Grid.

### Card Layout
The Bento Grid displays two cards stacked vertically (the `"TAMANHO TOTAL"` card was removed to simplify the interface):
1. **Hero Card**:
   - In user mode, it shows `"ARQUIVOS SALVOS EM"` with the date of the newest file in the backup set (formatted as `DD/MM/YYYY`).
   - In admin mode, it shows `"FONTE"` with the source summary describing the origins of the merged backups.
   - It is styled with a light blue background, constrained to a fixed size of `320x100px`, and its contents are centered horizontally and vertically.
2. **"ENCONTRADOS" Card**:
   - Displays the count of unique files found and the number of distinct folders (e.g. `"15 arquivos"`, `"Em 2 pastas"`).
   - Stacks directly below the Hero Card.
   - It is styled with a soft gray background, set to a fixed width of `320px`, and its contents are centered.
