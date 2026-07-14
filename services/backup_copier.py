from __future__ import annotations

"""Copy merged files to the user profile with progress, retry, and conflict handling.

Implements:
  - Chunk-by-chunk copy (1 MB buffer)
  - A small thread pool copying independent files concurrently
  - Retry with exponential backoff per file
  - Abort after N consecutive total failures
  - Silent skip of identical files (same name + size + mtime)
  - Conflict registration for differing files
  - Windows sleep prevention via SetThreadExecutionState
  - End-of-run retry for previously failed files

Example:
    result = copy_merged_files(files, progress_cb, cancel_event, retry_cfg)
"""
import ctypes
import logging
import os
import shutil
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from config import (
    CopyRetryConfig,
    COPY_CHUNK_BYTES,
    COPY_WORKERS,
)
from services.backup_merger import MergedFile

logger = logging.getLogger(__name__)

# Windows kernel32 constants for SetThreadExecutionState
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001

# Known profile folder mapping
PROFILE_FOLDER_MAP: dict[str, Path] = {
    "Desktop": Path.home() / "Desktop",
    "Documents": Path.home() / "Documents",
    "Downloads": Path.home() / "Downloads",
    "Pictures": Path.home() / "Pictures",
    "Music": Path.home() / "Music",
    "Videos": Path.home() / "Videos",
    "Favorites": Path.home() / "Favorites",
}

# Unmapped folders go here
_FALLBACK_ROOT = Path.home() / "Documents" / "Recuperados"


@dataclass
class SkippedFile:
    """A file that was not copied, with reason.

    Example:
        sf = SkippedFile(source=Path(...), dest=Path(...), reason="conflito")
    """
    source: Path
    dest: Path
    reason: str


@dataclass
class CopyResult:
    """Outcome of a copy operation.

    Example:
        if result.success and not result.skipped_files:
            print("All files restored")
    """
    success: bool
    files_copied: int
    bytes_copied: int
    skipped_files: list[SkippedFile] = field(default_factory=list)
    failed_files: list[SkippedFile] = field(default_factory=list)
    cancelled: bool = False
    duration_seconds: int = 0


# Type alias for the progress callback: (bytes_copied, total_bytes, filename)
ProgressCallback = Callable[[int, int, str], None]


class FileProgressTracker:
    """Track copy progress dynamically, supporting rollback on retries.

    Example:
        tracker = FileProgressTracker(progress_cb, total_bytes, filename, initial_bytes)
    """

    def __init__(
        self,
        progress_cb: ProgressCallback,
        total_bytes: int,
        filename: str,
        initial_bytes: int,
    ) -> None:
        self.progress_cb = progress_cb
        self.total_bytes = total_bytes
        self.filename = filename
        self.base_bytes = initial_bytes
        self.file_written = 0

    def on_chunk(self, chunk_len: int) -> None:
        """Accumulate bytes and emit progress.

        Example:
            tracker.on_chunk(8192)
        """
        self.file_written += chunk_len
        self.progress_cb(
            self.base_bytes + self.file_written,
            self.total_bytes,
            self.filename,
        )

    def reset_attempt(self) -> None:
        """Reset the bytes written for this file if a retry attempt starts.

        Example:
            tracker.reset_attempt()
        """
        self.file_written = 0


def resolve_dest_path(
    folder: str,
    relative_name: str,
    target_profile: Optional[str] = None,
) -> Path:
    """Map a backup folder + relative name to a local profile path."""
    if folder == "RAIZ":
        return Path("C:\\") / relative_name.replace("/", os.sep)
    if target_profile:
        return Path("C:\\Users") / target_profile / folder / relative_name.replace("/", os.sep)
    base = PROFILE_FOLDER_MAP.get(folder) or (_FALLBACK_ROOT / folder)
    return base / relative_name.replace("/", os.sep)


def _is_identical(source: Path, dest: Path) -> bool:
    """Check if source and dest are the same file (size + mtime)."""
    try:
        s_stat = source.stat()
        d_stat = dest.stat()
    except OSError:
        return False
    return (s_stat.st_size == d_stat.st_size
            and abs(s_stat.st_mtime - d_stat.st_mtime) < 2.0)


def _is_conflict(dest: Path) -> bool:
    return dest.exists()


def _needs_elevated_write(dest: Path) -> bool:
    """True when *dest* sits in another Windows user's profile folder and
    this process doesn't already hold an admin token — writing there must
    go through the elevated helper (see services/elevation.py) instead of
    a direct open()/rename(), which would raise PermissionError.
    """
    from services.elevation import is_admin
    if is_admin():
        return False
    try:
        rel = dest.relative_to("C:\\Users")
    except ValueError:
        return False
    profile = rel.parts[0] if rel.parts else ""
    return bool(profile) and profile.lower() != Path.home().name.lower()


def _prevent_sleep() -> None:
    """Keep Windows system awake during file copy."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS | _ES_SYSTEM_REQUIRED)
    except Exception:
        pass


def _allow_sleep() -> None:
    """Release the sleep prevention flag."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass


def _copy_single_file(
    source: Path,
    dest: Path,
    chunk_cb: Optional[Callable[[int], None]] = None,
    cancel_event: Optional[Event] = None,
) -> int:
    """Copy one file chunk-by-chunk, calling chunk_cb per chunk.

    Example:
        _copy_single_file(src, dest, tracker.on_chunk)
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0
    try:
        with open(source, "rb") as src, open(dest, "wb") as dst:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise OSError("Canceled by user")
                chunk = src.read(COPY_CHUNK_BYTES)
                if not chunk:
                    break
                dst.write(chunk)
                bytes_written += len(chunk)
                if chunk_cb:
                    chunk_cb(len(chunk))
    except Exception:
        if dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        raise
    _preserve_mtime(source, dest)
    return bytes_written


def _preserve_mtime(source: Path, dest: Path) -> None:
    """Copy the modification timestamp from source to dest."""
    try:
        stat = source.stat()
        os.utime(dest, (stat.st_atime, stat.st_mtime))
    except OSError:
        pass


def _try_copy_with_retry(
    source: Path,
    dest: Path,
    retry_cfg: CopyRetryConfig,
    tracker: Optional[FileProgressTracker] = None,
    cancel_event: Optional[Event] = None,
) -> tuple[bool, int, str]:
    """Attempt to copy a file with exponential backoff retries.

    Returns (success, bytes_written, error_message).
    """
    last_error = ""
    for attempt in range(retry_cfg.max_retries + 1):
        if cancel_event and cancel_event.is_set():
            return False, 0, "Canceled by user"
        if tracker:
            tracker.reset_attempt()
        try:
            chunk_cb = tracker.on_chunk if tracker else None
            written = _copy_single_file(source, dest, chunk_cb, cancel_event)
            return True, written, ""
        except OSError as exc:
            if cancel_event and cancel_event.is_set():
                return False, 0, "Canceled by user"
            last_error = f"{exc} (source={source})"
            if attempt < retry_cfg.max_retries:
                time.sleep(retry_cfg.backoff_base * (2 ** attempt))
    return False, 0, last_error


def copy_merged_files(
    files: list[MergedFile],
    progress_cb: ProgressCallback,
    cancel_event: Event,
    retry_cfg: CopyRetryConfig,
    cut_mode: bool = False,
) -> CopyResult:
    """Copy all *files* to the user profile with progress reporting."""
    from config import is_test_mode
    t0 = time.perf_counter()
    if is_test_mode():
        from services.backup_simulator import do_simulated_copy
        res = do_simulated_copy(files, progress_cb, cancel_event)
        res.duration_seconds = max(1, int(time.perf_counter() - t0))
        return res

    _prevent_sleep()
    try:
        res = _do_copy(files, progress_cb, cancel_event, retry_cfg, cut_mode)
        res.duration_seconds = max(1, int(time.perf_counter() - t0))
        return res
    finally:
        _allow_sleep()


def _delete_source_file(path: Path) -> None:
    """Safely delete a source file, clearing read-only attributes if necessary."""
    import stat
    try:
        path.chmod(stat.S_IWRITE)
    except OSError:
        pass
    try:
        path.unlink()
    except OSError as e:
        logger.error('{"event":"delete_source_failed","path":"%s","error":"%s"}', path, e)


def _copy_via_helper_with_retry(
    source: Path, dest: Path, retry_cfg: CopyRetryConfig, cut_mode: bool = False,
) -> tuple[bool, str]:
    """Retry an elevated-helper copy with the same exponential backoff as
    _try_copy_with_retry, so a transient IPC hiccup (e.g. the helper's pipe
    being briefly busy) doesn't count as a permanent failure on the first try.
    """
    from services.elevation import copy_via_helper
    last_error = ""
    for attempt in range(retry_cfg.max_retries + 1):
        ok, err = copy_via_helper(source, dest, cut_mode)
        if ok:
            return True, ""
        last_error = err
        if attempt < retry_cfg.max_retries:
            time.sleep(retry_cfg.backoff_base * (2 ** attempt))
    return False, last_error


def _mark_remaining_as_failed(remaining: list[MergedFile], failed: list[SkippedFile]) -> None:
    """Record files never attempted after an early abort, so the restore
    summary always accounts for every file instead of some silently vanishing.
    """
    for mf in remaining:
        dest = resolve_dest_path(mf.dest_folder, mf.relative_name, getattr(mf, "target_profile", None))
        failed.append(SkippedFile(
            mf.source_path, dest,
            "Não processado — operação interrompida após falhas consecutivas",
        ))


# One of "copied" (actually written), "neutral" (identical/conflict — not a
# failure, but doesn't count toward files_copied either), or "failed".
_FileOutcome = str


def _check_skip_or_conflict(
    mf: MergedFile, dest: Path, cut_mode: bool,
    skipped: list[SkippedFile], skipped_lock: threading.Lock,
) -> Optional[tuple[_FileOutcome, int]]:
    """Return a ("neutral", 0) outcome if *dest* is already identical or a
    genuine conflict, else None to signal the caller should actually copy.
    """
    if dest.exists() and _is_identical(mf.source_path, dest):
        if cut_mode:
            _delete_source_file(mf.source_path)
        return "neutral", 0

    if _is_conflict(dest):
        with skipped_lock:
            skipped.append(SkippedFile(
                source=mf.source_path, dest=dest,
                reason="já existia no destino com conteúdo diferente",
            ))
        return "neutral", 0
    return None


def _copy_elevated(
    mf: MergedFile, dest: Path, retry_cfg: CopyRetryConfig, cut_mode: bool,
    failed: list[SkippedFile], failed_lock: threading.Lock,
) -> tuple[_FileOutcome, int]:
    """Write via the elevated helper — dest is under another user's profile."""
    ok, err = _copy_via_helper_with_retry(mf.source_path, dest, retry_cfg, cut_mode)
    if ok:
        return "copied", mf.size_bytes
    with failed_lock:
        failed.append(SkippedFile(mf.source_path, dest, err))
    return "failed", 0


def _rename_for_cut_mode(source: Path, dest: Path) -> bool:
    """Try to move *source* to *dest* via a metadata-only rename (<1ms on the
    same drive) instead of a full copy-then-delete. Returns False (falls back
    to a regular copy) on any OSError, e.g. a cross-device move.
    """
    import stat
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            try:
                dest.chmod(stat.S_IWRITE)
            except OSError:
                pass
            try:
                dest.unlink()
            except OSError:
                pass
        os.rename(source, dest)
        return True
    except OSError as rename_exc:
        logger.warning('{"event":"rename_failed","source":"%s","dest":"%s","error":"%s"}', source, dest, rename_exc)
        return False


def _copy_local(
    mf: MergedFile, dest: Path, retry_cfg: CopyRetryConfig,
    cancel_event: Event, cut_mode: bool,
    failed: list[SkippedFile], failed_lock: threading.Lock,
) -> tuple[_FileOutcome, int]:
    """Write directly to *dest* (no elevation needed) with retry-with-backoff."""
    ok, wr, err = _try_copy_with_retry(mf.source_path, dest, retry_cfg, None, cancel_event)
    if ok:
        if cut_mode:
            _delete_source_file(mf.source_path)
        return "copied", wr
    with failed_lock:
        failed.append(SkippedFile(mf.source_path, dest, err))
    return "failed", 0


def _copy_one_file(
    mf: MergedFile, retry_cfg: CopyRetryConfig,
    skipped: list[SkippedFile], skipped_lock: threading.Lock,
    failed: list[SkippedFile], failed_lock: threading.Lock,
    cancel_event: Event, cut_mode: bool,
) -> tuple[_FileOutcome, int]:
    """Copy a single file end to end: skip/conflict check, elevated-profile
    routing, cut_mode rename, retry-with-backoff. Returns (outcome, bytes
    actually written). Safe to call from multiple threads concurrently —
    *skipped*/*failed* are shared lists, each guarded by its own lock; all
    other state here is local to this call.
    """
    dest = resolve_dest_path(mf.dest_folder, mf.relative_name, getattr(mf, "target_profile", None))

    skip_result = _check_skip_or_conflict(mf, dest, cut_mode, skipped, skipped_lock)
    if skip_result is not None:
        return skip_result

    if _needs_elevated_write(dest):
        return _copy_elevated(mf, dest, retry_cfg, cut_mode, failed, failed_lock)

    if cut_mode and _rename_for_cut_mode(mf.source_path, dest):
        return "copied", mf.size_bytes

    return _copy_local(mf, dest, retry_cfg, cancel_event, cut_mode, failed, failed_lock)


class _CopyAggregator:
    """Thread-safe running totals + consecutive-failure circuit breaker for
    the concurrent copy loop. Each file's outcome is applied atomically —
    "neutral" (identical/conflict) advances the byte total without touching
    files_copied or the failure streak; "copied" resets the streak; "failed"
    extends it and trips `aborted` once the configured limit is reached.
    """

    def __init__(self, total_bytes: int, progress_cb: ProgressCallback, consecutive_fail_limit: int) -> None:
        self._lock = threading.Lock()
        self._progress_cb = progress_cb
        self._consecutive_fail_limit = consecutive_fail_limit
        self._consecutive_fails = 0
        self.total_bytes = total_bytes
        self.copied_bytes = 0
        self.actual_bytes = 0
        self.copied_count = 0
        self.aborted = False

    def record(self, filename: str, size_bytes: int, actual_written: int, outcome: _FileOutcome) -> None:
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


def _process_copy_loop(
    files: list[MergedFile], tot_bytes: int, progress_cb: ProgressCallback,
    cancel_event: Event, retry_cfg: CopyRetryConfig,
    skipped: list[SkippedFile], failed: list[SkippedFile],
    cut_mode: bool = False,
) -> tuple[int, int, int, bool]:
    """Run the copy loop over a small thread pool — files are independent of
    each other, so copying several at once hides per-file overhead (syscalls,
    elevated-helper IPC round trips) that dominates over many small files.
    Returns (copied_bytes, actual_bytes, copied_count, aborted).
    """
    aggregator = _CopyAggregator(tot_bytes, progress_cb, retry_cfg.consecutive_fail_limit)
    skipped_lock = threading.Lock()
    failed_lock = threading.Lock()

    def run_one(mf: MergedFile) -> None:
        outcome, written = _copy_one_file(
            mf, retry_cfg, skipped, skipped_lock, failed, failed_lock, cancel_event, cut_mode,
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

    if cancel_event.is_set() or aggregator.aborted:
        if aggregator.aborted:
            logger.error('{"event":"copy_abort"}')
        _mark_remaining_as_failed(files[submitted:], failed)
        return aggregator.copied_bytes, aggregator.actual_bytes, aggregator.copied_count, True
    return aggregator.copied_bytes, aggregator.actual_bytes, aggregator.copied_count, False


def _do_copy(
    files: list[MergedFile], progress_cb: ProgressCallback,
    cancel_event: Event, retry_cfg: CopyRetryConfig,
    cut_mode: bool = False,
) -> CopyResult:
    """Inner copy loop — separated so sleep flag is always released."""
    tot_bytes = sum(f.size_bytes for f in files)
    skipped: list[SkippedFile] = []
    failed: list[SkippedFile] = []
    copied_bytes, actual_bytes, copied_count, aborted = _process_copy_loop(
        files, tot_bytes, progress_cb, cancel_event, retry_cfg, skipped, failed, cut_mode
    )
    if aborted and not cancel_event.is_set():
        return CopyResult(False, copied_count, actual_bytes, skipped, failed, False)
    if cancel_event.is_set():
        return CopyResult(False, copied_count, actual_bytes, skipped, failed, True)
    if failed:
        copied_count, copied_bytes, actual_bytes = _retry_failed_files(
            failed, progress_cb, retry_cfg, cancel_event, copied_count, copied_bytes, actual_bytes, tot_bytes, cut_mode
        )
    return CopyResult(True, copied_count, actual_bytes, skipped, failed, False)


def _retry_single_failed_file(
    sf: SkippedFile, progress_cb: ProgressCallback,
    retry_cfg: CopyRetryConfig, copied_bytes: int, total_bytes: int,
    cancel_event: Optional[Event] = None,
) -> tuple[bool, int, str]:
    """Retry copying a single failed file."""
    try:
        file_size = sf.source.stat().st_size
    except OSError:
        file_size = 0
    base_bytes = copied_bytes - file_size
    if _needs_elevated_write(sf.dest):
        ok, err = _copy_via_helper_with_retry(sf.source, sf.dest, retry_cfg)
        new_bytes = base_bytes + file_size if ok else copied_bytes
        progress_cb(new_bytes, total_bytes, sf.source.name)
        return ok, new_bytes, err
    tr = FileProgressTracker(progress_cb, total_bytes, sf.source.name, base_bytes)
    ok, w, err = _try_copy_with_retry(sf.source, sf.dest, retry_cfg, tr, cancel_event)
    new_bytes = base_bytes + w if ok else copied_bytes
    return ok, new_bytes, err


def _retry_failed_files(
    failed: list[SkippedFile], progress_cb: ProgressCallback,
    retry_cfg: CopyRetryConfig, cancel_event: Event,
    copied_count: int, copied_bytes: int, actual_bytes: int, total_bytes: int,
    cut_mode: bool = False,
) -> tuple[int, int, int]:
    """Retry previously failed files once more."""
    for sf in list(failed):
        if cancel_event.is_set():
            break
        ok, new_bytes, err = _retry_single_failed_file(
            sf, progress_cb, retry_cfg, copied_bytes, total_bytes, cancel_event
        )
        if ok:
            if cut_mode:
                _delete_source_file(sf.source)
            try:
                file_size = sf.source.stat().st_size
            except OSError:
                file_size = 0
            copied_count += 1
            copied_bytes = new_bytes
            actual_bytes += file_size
            failed.remove(sf)
        else:
            sf.reason = err
        progress_cb(copied_bytes, total_bytes, sf.source.name)
    return copied_count, copied_bytes, actual_bytes


def copy_skipped_to_desktop(skipped_files: list[SkippedFile]) -> tuple[bool, str]:
    """Copy conflicting files to a Desktop folder for manual review.

    Creates Desktop\\Remos - Arquivos Pulados\\{folder}\\ structure.

    Example:
        ok, msg = copy_skipped_to_desktop(result.skipped_files)
    """
    from config import is_test_mode, get_app_name
    if is_test_mode():
        time.sleep(1.0)
        desktop = Path.home() / "Desktop"
        target_root = desktop / f"{get_app_name()} - Arquivos Pulados (Simulado)"
        return True, str(target_root)

    desktop = Path.home() / "Desktop"
    target_root = desktop / f"{get_app_name()} - Arquivos Pulados"

    try:
        for sf in skipped_files:
            # Determine subfolder from original dest relative to profile
            rel = _relative_to_profile(sf.dest)
            dest = target_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(sf.source), str(dest))
    except OSError as exc:
        msg = f"Erro ao copiar arquivos pulados: {exc}"
        logger.error('{"event":"copy_skipped_failed","error":"%s"}', exc)
        return False, msg

    return True, str(target_root)


def _relative_to_profile(dest_path: Path) -> Path:
    """Extract the profile-relative path for organizing skipped files."""
    home = Path.home()
    try:
        return dest_path.relative_to(home)
    except ValueError:
        return Path(dest_path.name)
