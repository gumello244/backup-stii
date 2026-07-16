from __future__ import annotations

"""Service to copy local user profiles and disk root folders to the backup target.

Reuses core copy mechanisms, sleep prevention, and progress tracking from
services/backup_copier.py to ensure DRY. Implements UAC read elevation
via services/elevation.py, file filtering, installed programs report,
and HTML profile tree report generation.
"""

import fnmatch
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, FIRST_COMPLETED, wait
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from config import (
    CopyRetryConfig,
    COPY_CHUNK_BYTES,
    COPY_WORKERS,
)
from services.backup_merger import MergedFile
from services.backup_copier import (
    _is_identical,
    _copy_single_file,
    _try_copy_with_retry,
    _prevent_sleep,
    _allow_sleep,
    FileProgressTracker,
    SkippedFile,
    CopyResult,
)
from services.elevation import is_admin, copy_via_helper

logger = logging.getLogger(__name__)

# Excluded patterns matching backup.sh exclusions when skip_media_exec is True
_EXCLUDED_PATTERNS = [
    "desktop.ini", "thumbs.db", ".ds_store", "*.lnk",
    "*.mpg", "*.mp3", "*.wav", "*.mpeg", "*.mp4", "*.avi", "*.mkv", "*.3gp",
    "*.mov", "*.wmv", "*.exe", "*.msi", "*.vbs", "*.dll", "*.bak", "*.dat",
    "*.cab", "*.CAB"
]


def should_skip_file(name: str) -> bool:
    """True if filename matches any ignored pattern."""
    name_lower = name.lower()
    return any(fnmatch.fnmatch(name_lower, pattern.lower()) for pattern in _EXCLUDED_PATTERNS)


def _needs_elevated_read(src: Path) -> bool:
    """True when src sits in another user's profile and needs admin privileges to read."""
    if is_admin():
        return False
    try:
        rel = src.relative_to("C:\\Users")
    except ValueError:
        return False
    profile = rel.parts[0] if rel.parts else ""
    return bool(profile) and profile.lower() != Path.home().name.lower()


def resolve_backup_dest_path(
    dest_root: Path,
    folder: str,
    relative_name: str,
    target_profile: Optional[str] = None,
) -> Path:
    """Map a source folder + relative name to the correct backup structure."""
    if folder == "RAIZ":
        return dest_root / "RAIZ" / relative_name.replace("/", os.sep)
    profile = target_profile or "Default"
    return dest_root / "USUARIOS" / profile / folder / relative_name.replace("/", os.sep)


class _BackupProgressAggregator:
    """Thread-safe progress aggregator for backup copy loop."""

    def __init__(self, total_bytes: int, progress_cb: Callable[[int, int, str], None], consecutive_fail_limit: int) -> None:
        self._lock = threading.Lock()
        self._progress_cb = progress_cb
        self._consecutive_fail_limit = consecutive_fail_limit
        self._consecutive_fails = 0
        self.total_bytes = total_bytes
        self.copied_bytes = 0
        self.actual_bytes = 0
        self.copied_count = 0
        self.aborted = False

    def record(self, filename: str, size_bytes: int, actual_written: int, outcome: str) -> None:
        with self._lock:
            self.copied_bytes += size_bytes
            self.actual_bytes += actual_written
            if outcome == "copied":
                self.copied_count += 1
                self._consecutive_fails = 0
            elif outcome == "failed":
                self._consecutive_fails += 1
                if self._consecutive_fails >= self._consecutive_fail_limit:
                    self.aborted = True
            self._progress_cb(self.copied_bytes, self.total_bytes, filename)


def _backup_one_file(
    mf: MergedFile,
    dest_root: Path,
    retry_cfg: CopyRetryConfig,
    skipped: list[SkippedFile],
    skipped_lock: threading.Lock,
    failed: list[SkippedFile],
    failed_lock: threading.Lock,
    cancel_event: Event,
) -> tuple[str, int]:
    """Process a single file backup: identical check, UAC read elevation routing, and copying."""
    dest = resolve_backup_dest_path(dest_root, mf.dest_folder, mf.relative_name, mf.target_profile)

    # Identical check
    if dest.exists() and _is_identical(mf.source_path, dest):
        return "neutral", 0

    # Elevated read check
    if _needs_elevated_read(mf.source_path):
        ok, err = copy_via_helper(mf.source_path, dest, cut_mode=False)
        if ok:
            return "copied", mf.size_bytes
        with failed_lock:
            failed.append(SkippedFile(mf.source_path, dest, err))
        return "failed", 0

    # Standard copy
    ok, wr, err = _try_copy_with_retry(mf.source_path, dest, retry_cfg, None, cancel_event)
    if ok:
        return "copied", wr
    with failed_lock:
        failed.append(SkippedFile(mf.source_path, dest, err))
    return "failed", 0


def backup_local_data(
    files: list[MergedFile],
    dest_root: Path,
    progress_cb: Callable[[int, int, str], None],
    cancel_event: Event,
    retry_cfg: CopyRetryConfig,
    skip_media_exec: bool = False,
) -> CopyResult:
    """Copy all selected local files to the backup destination."""
    t0 = time.perf_counter()
    from config import is_test_mode
    if is_test_mode():
        # Reuse simulation logic
        from services.backup_simulator import do_simulated_copy
        res = do_simulated_copy(files, progress_cb, cancel_event)
        res.duration_seconds = max(1, int(time.perf_counter() - t0))
        return res

    _prevent_sleep()
    try:
        # Pre-filter exclusions if requested
        if skip_media_exec:
            files = [f for f in files if not should_skip_file(f.source_path.name)]

        tot_bytes = sum(f.size_bytes for f in files)
        skipped: list[SkippedFile] = []
        failed: list[SkippedFile] = []

        aggregator = _BackupProgressAggregator(tot_bytes, progress_cb, retry_cfg.consecutive_fail_limit)
        skipped_lock = threading.Lock()
        failed_lock = threading.Lock()

        def run_one(mf: MergedFile) -> None:
            outcome, written = _backup_one_file(
                mf, dest_root, retry_cfg, skipped, skipped_lock, failed, failed_lock, cancel_event
            )
            aggregator.record(mf.relative_name, mf.size_bytes, written, outcome)

        submitted = 0
        with ThreadPoolExecutor(max_workers=COPY_WORKERS) as executor:
            pending: dict = {}
            for mf in files:
                if cancel_event.is_set() or aggregator.aborted:
                    break
                pending[executor.submit(run_one, mf)] = mf
                submitted += 1
                if len(pending) >= COPY_WORKERS:
                    done, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
                    for f in done:
                        pending.pop(f, None)
            wait(pending.keys())

        # Generate reports after backup copy loop finishes
        if not cancel_event.is_set() and not aggregator.aborted:
            try:
                generate_installed_programs_report(dest_root)
            except Exception as e:
                logger.error('{"event":"backup_report_failed","report":"programs","error":"%s"}', e)

            # Generate HTML trees for each backup profile
            profiles = {f.target_profile for f in files if f.target_profile}
            for profile in profiles:
                try:
                    profile_dir = dest_root / "USUARIOS" / profile
                    if profile_dir.is_dir():
                        generate_profile_html_tree(profile_dir, profile_dir / f"Relatorio_{profile}.html", profile)
                except Exception as e:
                    logger.error('{"event":"backup_report_failed","report":"html_tree","profile":"%s","error":"%s"}', profile, e)

        cancelled = cancel_event.is_set()
        success = not cancelled and not aggregator.aborted

        # Mark remaining files as failed on abort
        if not success:
            for mf in files[submitted:]:
                dest = resolve_backup_dest_path(dest_root, mf.dest_folder, mf.relative_name, mf.target_profile)
                failed.append(SkippedFile(mf.source_path, dest, "Operação abortada ou cancelada"))

        duration = max(1, int(time.perf_counter() - t0))
        return CopyResult(
            success=success,
            files_copied=aggregator.copied_count,
            bytes_copied=aggregator.actual_bytes,
            skipped_files=skipped,
            failed_files=failed,
            cancelled=cancelled,
            duration_seconds=duration,
        )
    finally:
        _allow_sleep()


# ------------------------------------------------------------------
# Report generation helpers
# ------------------------------------------------------------------

def generate_installed_programs_report(dest_root: Path) -> None:
    """Create Programas_Instalados.txt file in the backup destination."""
    dest_root.mkdir(parents=True, exist_ok=True)
    report_file = dest_root / "Programas_Instalados.txt"

    lines = [f"=== RELAÇÃO DE PASTAS DE PROGRAMAS ({time.strftime('%d/%m/%Y')}) ==="]

    for path_str, label in [("C:\\Program Files", "Program Files"), ("C:\\Program Files (x86)", "Program Files (x86)")]:
        lines.append(f"\n\n--- {label} ---")
        p = Path(path_str)
        if p.is_dir():
            try:
                for entry in sorted(p.iterdir(), key=lambda x: x.name.lower()):
                    if entry.is_dir():
                        lines.append(entry.name)
            except OSError:
                pass

    menu_path = Path("C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs")
    lines.append("\n\n--- Atalhos do Menu Iniciar ---")
    if menu_path.is_dir():
        try:
            for entry in sorted(menu_path.rglob("*")):
                if entry.is_file() and entry.suffix.lower() == ".lnk":
                    lines.append(str(entry.relative_to(menu_path)))
        except OSError:
            pass

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def generate_profile_html_tree(user_dir: Path, output_file: Path, user_name: str) -> None:
    """Generate a clean, portable HTML tree report listing all files in user_dir."""
    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"  <title>Relatório de Backup - {user_name}</title>",
        "  <style>",
        "    body { font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; color: #1A202C; background-color: #F9F9F9; }",
        "    h1 { font-size: 20px; color: #3B6EA5; margin-bottom: 5px; }",
        "    .timestamp { font-size: 12px; color: #718096; margin-bottom: 20px; }",
        "    ul { list-style-type: none; padding-left: 20px; }",
        "    li { margin: 4px 0; position: relative; }",
        "    .folder { font-weight: bold; color: #2C5282; }",
        "    .file { color: #4A5568; font-size: 13px; }",
        "    .size { color: #718096; font-size: 11px; margin-left: 8px; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>Relatório de Arquivos Salvos para o Usuário: {user_name}</h1>",
        f"  <div class='timestamp'>Gerado em {time.strftime('%d/%m/%Y %H:%M:%S')}</div>",
        "  <ul>"
    ]

    def format_bytes(b: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    def walk_html(current_path: Path) -> list[str]:
        lines = []
        try:
            entries = sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                # Do not list the report itself
                if entry == output_file:
                    continue
                if entry.is_dir():
                    lines.append(f"<li><span class='folder'>📁 {entry.name}</span>")
                    lines.append("  <ul>")
                    lines.extend(walk_html(entry))
                    lines.append("  </ul>")
                    lines.append("</li>")
                elif entry.is_file():
                    sz = ""
                    try:
                        sz = format_bytes(entry.stat().st_size)
                    except OSError:
                        pass
                    lines.append(f"<li><span class='file'>📄 {entry.name}</span><span class='size'>({sz})</span></li>")
        except OSError:
            pass
        return lines

    html_lines.extend(walk_html(user_dir))
    html_lines.extend([
        "  </ul>",
        "</body>",
        "</html>"
    ])

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(html_lines))
