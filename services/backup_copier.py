from __future__ import annotations

"""Copy merged files to the user profile with progress, retry, and conflict handling.

Implements:
  - Chunk-by-chunk copy (8 KB buffer)
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
import time
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Callable, Optional

from config import (
    CopyRetryConfig,
    BENCHMARK_FILE_BYTES,
    BENCHMARK_BLOCK_BYTES,
    LOCAL_SPEED_FALLBACK_BPS,
    NETWORK_SPEED_FALLBACK_BPS,
    WRITE_SPEED_CAP_BPS,
)
from services.backup_merger import MergedFile

logger = logging.getLogger(__name__)

# 8 KB read/write buffer — balances speed vs. memory on old machines
_CHUNK_SIZE = 8192

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
                chunk = src.read(_CHUNK_SIZE)
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
        res = _do_copy(files, progress_cb, cancel_event, retry_cfg)
        res.duration_seconds = max(1, int(time.perf_counter() - t0))
        return res
    finally:
        _allow_sleep()


def _check_skip_or_conflict(
    mf: MergedFile, dest: Path, total_bytes: int,
    copied_bytes: int, progress_cb: ProgressCallback,
    skipped: list[SkippedFile],
) -> Optional[int]:
    """Check if identical or conflict, returning new_bytes if handled."""
    if dest.exists() and _is_identical(mf.source_path, dest):
        new_bytes = copied_bytes + mf.size_bytes
        progress_cb(new_bytes, total_bytes, mf.relative_name)
        return new_bytes
    if _is_conflict(dest):
        skipped.append(SkippedFile(
            source=mf.source_path, dest=dest,
            reason="já existia no destino com conteúdo diferente",
        ))
        new_bytes = copied_bytes + mf.size_bytes
        progress_cb(new_bytes, total_bytes, mf.relative_name)
        return new_bytes
    return None


def _copy_file_step(
    mf: MergedFile, total_bytes: int, copied_bytes: int,
    progress_cb: ProgressCallback, retry_cfg: CopyRetryConfig,
    skipped: list[SkippedFile], failed: list[SkippedFile],
    cancel_event: Event,
) -> tuple[int, bool, bool]:
    """Copy one file, returning (new_bytes, actual_written, reset_fails, inc_fails)."""
    dest = resolve_dest_path(mf.dest_folder, mf.relative_name, getattr(mf, "target_profile", None))
    res = _check_skip_or_conflict(mf, dest, total_bytes, copied_bytes, progress_cb, skipped)
    if res is not None:
        return res, 0, False, False
    progress_cb(copied_bytes, total_bytes, mf.relative_name)
    tr = FileProgressTracker(progress_cb, total_bytes, mf.relative_name, copied_bytes)
    ok, wr, err = _try_copy_with_retry(mf.source_path, dest, retry_cfg, tr, cancel_event)
    if ok:
        return copied_bytes + wr, wr, True, False
    failed.append(SkippedFile(mf.source_path, dest, err))
    return copied_bytes + mf.size_bytes, 0, False, True


def _process_copy_loop(
    files: list[MergedFile], tot_bytes: int, progress_cb: ProgressCallback,
    cancel_event: Event, retry_cfg: CopyRetryConfig,
    skipped: list[SkippedFile], failed: list[SkippedFile],
) -> tuple[int, int, int, bool]:
    """Run copy loop, returning (copied_bytes, actual_bytes, copied_count, aborted)."""
    copied_bytes, actual_bytes, copied_count, consecutive_fails = 0, 0, 0, 0
    for mf in files:
        if cancel_event.is_set():
            return copied_bytes, actual_bytes, copied_count, True
        copied_bytes, wr, reset_f, inc_f = _copy_file_step(
            mf, tot_bytes, copied_bytes, progress_cb, retry_cfg, skipped, failed, cancel_event
        )
        consecutive_fails = 0 if reset_f else (consecutive_fails + 1 if inc_f else consecutive_fails)
        actual_bytes += wr
        if reset_f:
            copied_count += 1
        if consecutive_fails >= retry_cfg.consecutive_fail_limit:
            logger.error('{"event":"copy_abort","consecutive_fails":%d}', consecutive_fails)
            return copied_bytes, actual_bytes, copied_count, True
    return copied_bytes, actual_bytes, copied_count, False


def _do_copy(
    files: list[MergedFile], progress_cb: ProgressCallback,
    cancel_event: Event, retry_cfg: CopyRetryConfig,
) -> CopyResult:
    """Inner copy loop — separated so sleep flag is always released."""
    tot_bytes = sum(f.size_bytes for f in files)
    skipped: list[SkippedFile] = []
    failed: list[SkippedFile] = []
    copied_bytes, actual_bytes, copied_count, aborted = _process_copy_loop(
        files, tot_bytes, progress_cb, cancel_event, retry_cfg, skipped, failed
    )
    if aborted and not cancel_event.is_set():
        return CopyResult(False, copied_count, actual_bytes, skipped, failed, False)
    if cancel_event.is_set():
        return CopyResult(False, copied_count, actual_bytes, skipped, failed, True)
    if failed:
        copied_count, copied_bytes, actual_bytes = _retry_failed_files(
            failed, progress_cb, retry_cfg, cancel_event, copied_count, copied_bytes, actual_bytes, tot_bytes
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
    tr = FileProgressTracker(progress_cb, total_bytes, sf.source.name, base_bytes)
    ok, w, err = _try_copy_with_retry(sf.source, sf.dest, retry_cfg, tr, cancel_event)
    new_bytes = base_bytes + w if ok else copied_bytes
    return ok, new_bytes, err


def _retry_failed_files(
    failed: list[SkippedFile], progress_cb: ProgressCallback,
    retry_cfg: CopyRetryConfig, cancel_event: Event,
    copied_count: int, copied_bytes: int, actual_bytes: int, total_bytes: int,
) -> tuple[int, int, int]:
    """Retry previously failed files once more."""
    for sf in list(failed):
        if cancel_event.is_set():
            break
        ok, new_bytes, err = _retry_single_failed_file(
            sf, progress_cb, retry_cfg, copied_bytes, total_bytes, cancel_event
        )
        if ok:
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





def _do_write_benchmark(test_file: Path) -> int:
    """Perform actual write speed test, returning bytes per second."""
    block_count = BENCHMARK_FILE_BYTES // BENCHMARK_BLOCK_BYTES
    data = b"A" * BENCHMARK_BLOCK_BYTES
    with open(test_file, "wb") as f:
        t0 = time.perf_counter()
        for _ in range(block_count):
            f.write(data)
        dur = max(0.001, time.perf_counter() - t0)
    return int(BENCHMARK_FILE_BYTES / dur)


def run_write_benchmark(target_dir: Path) -> int:
    """Measure disk write speed in target_dir by writing a temporary file.

    Returns speed in bytes/sec. Fallback to 80 MB/s for network, 50 MB/s for local on error.
    """
    from config import is_test_mode
    if is_test_mode():
        return NETWORK_SPEED_FALLBACK_BPS
    is_net = target_dir.drive.startswith("\\\\") or target_dir.as_posix().startswith("//")
    fallback = NETWORK_SPEED_FALLBACK_BPS if is_net else LOCAL_SPEED_FALLBACK_BPS
    test_file = target_dir / f".remos_speedtest_{int(time.time())}"
    logger.debug('{"event":"benchmark_start","path":"%s"}', test_file)
    try:
        speed = _do_write_benchmark(test_file)
        test_file.unlink(missing_ok=True)
        logger.info('{"event":"benchmark_success","path":"%s","speed":%d}', test_file, speed)
        return speed
    except OSError as exc:
        logger.warning('{"event":"benchmark_failed","path":"%s","error":"%s"}', test_file, exc)
        return fallback


def estimate_copy_seconds_for_files(
    files: list[MergedFile], write_speed_bps: int,
    network_speed_bps: Optional[int] = None,
) -> int:
    """Calculate total estimated copy time by summing individual file durations.

    Network files are limited by the minimum of local write and network speeds.
    """
    total_seconds = 0.0
    net_speed = network_speed_bps or NETWORK_SPEED_FALLBACK_BPS
    write_cap = min(write_speed_bps, WRITE_SPEED_CAP_BPS)
    for mf in files:
        is_net = (
            mf.source_path.drive.startswith("\\\\")
            or mf.source_path.as_posix().startswith("//")
        )
        speed = min(write_cap, net_speed) if is_net else write_cap
        total_seconds += mf.size_bytes / max(1.0, speed)
    return max(1, int(total_seconds))
