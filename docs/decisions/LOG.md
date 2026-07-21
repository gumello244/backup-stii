# Architecture Decisions Log

Format: `YYYY-MM-DD | decision | why | supersedes`

- 2026-07-20 | Persistent Low-Integrity SDDL Named Pipe IPC helper for UAC elevation | Avoids running full PyQt5 GUI as Administrator; reduces UAC prompt to 1 per admin session and reuses pipe handle ([services/elevation.py:55](file:///c:/Users/100229/Documents/OC/Remos/services/elevation.py#L55)) | Repeated UAC prompts / relaunching main app elevated
- 2026-07-20 | Fire-and-forget Async HTTP Telemetry Client (`ApiService`) | Ensures backend telemetry lag or failure never blocks desktop UX or restore workflows ([services/api_service.py:80](file:///c:/Users/100229/Documents/OC/Remos/services/api_service.py#L80)) | Blocking telemetry HTTP calls
- 2026-07-20 | Dedicated Configuration Module (`config.py`) | Keeps sensitive credentials strictly in `app_secrets.py` while providing typed dataclass configuration objects for testability ([config.py:100](file:///c:/Users/100229/Documents/OC/Remos/config.py#L100)) | Scattered `app_secrets.py` direct imports
- 2026-07-20 | Discovery Cache with 30s TTL (`DISCOVERY_CACHE_TTL_SECONDS`) | Prevents network share SMB query flooding during rapid admin search filter input ([services/admin_backup_discovery.py:30](file:///c:/Users/100229/Documents/OC/Remos/services/admin_backup_discovery.py#L30)) | Uncached network directory scanning
- 2026-07-20 | Multi-worker `ThreadPoolExecutor` (max 4) for indexing and copying | Balances small-file IPC round trips and SMB throughput without overloading network interfaces ([config.py:45](file:///c:/Users/100229/Documents/OC/Remos/config.py#L45)) | Sequential file-by-file copy loop
