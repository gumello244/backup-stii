from __future__ import annotations

"""Background workers for Remos — mirrors SONICO's concurrency pattern.

GlobalAsyncWorker: singleton QThread with a persistent asyncio event loop.
ThreadedWorker: QThread base for blocking I/O (file copy).
Task-specific workers bridge services → UI via Qt signals.

Example:
    worker = get_global_worker()
    worker.submit_task(api_service.report_startup())
"""
import asyncio
import logging
import threading
from concurrent.futures import Future
from pathlib import Path
from threading import Event
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal, QRunnable, QObject

from config import (
    get_api_config, get_server_config, get_copy_retry_config,
    CopyRetryConfig,
)
from services.api_service import ApiService
from services.backup_copier import CopyResult, SkippedFile
from services.backup_discovery import BackupSource
from services.backup_merger import MergedFile, MergedFileSet

logger = logging.getLogger(__name__)


# =====================================================================
# Global Async Worker — singleton persistent event loop
# =====================================================================


class GlobalAsyncWorker(threading.Thread):
    """Persistent background thread with an asyncio event loop.

    Example:
        w = GlobalAsyncWorker()  # starts automatically
        w.submit_task(some_coroutine())
    """

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._api_service: Optional[ApiService] = None
        self._pending: list[object] = []
        self._lock = threading.Lock()
        self.start()

    def run(self) -> None:
        """Thread entry: create loop, init services, run forever."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self._api_service = ApiService(get_api_config())
        self.submit_task(self._api_service.report_startup())

        with self._lock:
            for coro in self._pending:
                asyncio.run_coroutine_threadsafe(coro, self.loop)
            self._pending.clear()

        self.loop.run_forever()
        self._cleanup()

    def _cleanup(self) -> None:
        """Shutdown sequence — report + close HTTP client."""
        if self._api_service:
            try:
                self.loop.run_until_complete(
                    self._api_service.report_shutdown(),
                )
            except Exception:
                pass
            self.loop.run_until_complete(self._api_service.close())
        self.loop.close()

    def submit_task(self, coro: object) -> Optional[Future]:
        """Schedule a coroutine on the background loop.

        Example:
            worker.submit_task(api.report_success("RESTORE", {}))
        """
        with self._lock:
            if self.loop and not self.loop.is_closed():
                try:
                    return asyncio.run_coroutine_threadsafe(coro, self.loop)
                except RuntimeError:
                    return None
            self._pending.append(coro)
            return None

    def stop(self) -> None:
        """Gracefully stop the event loop and wait for thread exit."""
        if self.loop and not self.loop.is_closed():
            try:
                self.loop.call_soon_threadsafe(self.loop.stop)
            except RuntimeError:
                pass
        self.join(timeout=1.0)

    @property
    def api_service(self) -> Optional[ApiService]:
        return self._api_service


# Singleton
_global_worker: Optional[GlobalAsyncWorker] = None


def get_global_worker() -> GlobalAsyncWorker:
    """Lazy-init singleton for the global async worker.

    Example:
        worker = get_global_worker()
    """
    global _global_worker
    if _global_worker is None:
        _global_worker = GlobalAsyncWorker()
    return _global_worker


# =====================================================================
# Threaded Worker — for blocking sync operations
# =====================================================================


class ThreadedWorker(QThread):
    """Base QThread for heavy blocking operations (file I/O, subprocess).

    Example:
        class MyWorker(ThreadedWorker):
            finished = pyqtSignal(bool)
            def run(self): ...
    """
    error = pyqtSignal(str)


# =====================================================================
# Task-specific workers
# =====================================================================


class DiscoverSourcesWorker(ThreadedWorker):
    """Scan network + local for backup sources in a background thread.

    Example:
        w = DiscoverSourcesWorker(admin_mode=False)
        w.finished.connect(on_sources_found)
        w.start()
    """
    finished = pyqtSignal(list)  # list[BackupSource]

    def __init__(self, admin_mode: bool = False) -> None:
        """Initialize the discover worker with admin mode toggle.

        Example:
            w = DiscoverSourcesWorker(admin_mode=False)
        """
        super().__init__()
        self._admin_mode = admin_mode

    def run(self) -> None:
        """Run discovery logic in the background thread.

        Example:
            worker.start()
        """
        try:
            from services.backup_discovery import discover_all_sources
            cfg = get_server_config()
            sources = discover_all_sources(
                cfg.server_ip, cfg.backup_share, admin_mode=self._admin_mode
            )
            self.finished.emit(sources)
        except Exception as exc:
            logger.error('{"event":"discover_error","error":"%s"}', exc)
            self.error.emit(str(exc))
            self.finished.emit([])


class AdminDiscoverSourcesWorker(ThreadedWorker):
    """Scan network + local for admin backup sources, emitting incrementally.

    Example:
        w = AdminDiscoverSourcesWorker(custom_query="14029")
        w.source_found.connect(on_source_found)
        w.start()
    """
    source_found = pyqtSignal(object)  # AdminBackupSource
    stage_changed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, custom_query: Optional[str] = None) -> None:
        super().__init__()
        self._custom_query = custom_query
        self._cancel = Event()

    def request_cancel(self) -> None:
        """Ask a still-running scan to stop at its next checkpoint.

        Example:
            worker.request_cancel()
        """
        self._cancel.set()

    def run(self) -> None:
        try:
            from services.admin_backup_discovery import scan_admin_backups
            cfg = get_server_config()
            for src in scan_admin_backups(
                cfg.server_ip, cfg.backup_share, self._custom_query,
                stage_cb=self.stage_changed.emit,
                cancel_event=self._cancel,
            ):
                self.source_found.emit(src)
        except Exception as exc:
            logger.error('{"event":"admin_discover_error","error":"%s"}', exc)
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class MergeSourcesWorker(ThreadedWorker):
    """Merge multiple backup sources into an optimal file set.

    Example:
        w = MergeSourcesWorker(sources, admin_mode=False)
        w.finished.connect(on_merged)
        w.start()
    """
    finished = pyqtSignal(object)  # MergedFileSet

    def __init__(self, sources: list[BackupSource], admin_mode: bool = False) -> None:
        super().__init__()
        self._sources = sources
        self._admin_mode = admin_mode

    def run(self) -> None:
        try:
            from services.backup_merger import merge_sources
            result = merge_sources(self._sources, admin_mode=self._admin_mode)
            self.finished.emit(result)
        except Exception as exc:
            logger.error('{"event":"merge_error","error":"%s"}', exc)
            self.error.emit(str(exc))
            from services.backup_merger import MergedFileSet
            self.finished.emit(
                MergedFileSet(files=[], total_bytes=0, source_summary="Erro"),
            )


class CopyFilesWorker(ThreadedWorker):
    """Copy merged files to user profile with progress reporting.

    Example:
        w = CopyFilesWorker(files)
        w.progress.connect(update_bar)
        w.finished.connect(on_done)
        w.start()
    """
    # bytes_copied, total_bytes, current_filename
    progress = pyqtSignal(float, float, str)
    finished = pyqtSignal(object)  # CopyResult

    def __init__(
        self,
        files: list[MergedFile],
        retry_cfg: Optional[CopyRetryConfig] = None,
        cut_mode: bool = False,
    ) -> None:
        super().__init__()
        self._files = files
        self._cancel = Event()
        self._retry_cfg = retry_cfg or get_copy_retry_config()
        self._cut_mode = cut_mode

    def run(self) -> None:
        try:
            from services.backup_copier import copy_merged_files
            result = copy_merged_files(
                self._files,
                progress_cb=self._on_progress,
                cancel_event=self._cancel,
                retry_cfg=self._retry_cfg,
                cut_mode=self._cut_mode,
            )
            self.finished.emit(result)
        except Exception as exc:
            logger.error('{"event":"copy_error","error":"%s"}', exc)
            self.error.emit(str(exc))
            self.finished.emit(CopyResult(
                success=False, files_copied=0, bytes_copied=0,
                cancelled=False,
            ))

    def _on_progress(self, copied: int, total: int, filename: str) -> None:
        """Bridge progress callback to Qt signal (thread-safe).

        Example:
            self._on_progress(1024, 2048, "file.txt")
        """
        self.progress.emit(float(copied), float(total), filename)

    def request_cancel(self) -> None:
        """Request graceful cancellation of the copy."""
        self._cancel.set()


class CopySkippedWorker(ThreadedWorker):
    """Copy skipped/conflicting files to a Desktop folder.

    Example:
        w = CopySkippedWorker(skipped_files)
        w.finished.connect(on_done)
        w.start()
    """
    finished = pyqtSignal(bool, str)  # success, message_or_path

    def __init__(self, skipped_files: list[SkippedFile]) -> None:
        super().__init__()
        self._skipped = skipped_files

    def run(self) -> None:
        try:
            from services.backup_copier import copy_skipped_to_desktop
            ok, msg = copy_skipped_to_desktop(self._skipped)
            self.finished.emit(ok, msg)
        except Exception as exc:
            logger.error('{"event":"copy_skipped_error","error":"%s"}', exc)
            self.finished.emit(False, str(exc))


class BenchmarkWorker(ThreadedWorker):
    """Run write benchmarks in a background thread to prevent UI freezing."""
    finished = pyqtSignal(float, float)  # local_speed, network_speed

    def __init__(self, local_path: Path, network_path: Optional[Path] = None) -> None:
        super().__init__()
        self._local_path = local_path
        self._network_path = network_path

    def run(self) -> None:
        from services.copy_benchmark import run_write_benchmark
        local_speed = run_write_benchmark(self._local_path)
        net_speed = 0
        if self._network_path:
            net_speed = run_write_benchmark(self._network_path)
        self.finished.emit(float(local_speed), float(net_speed))


class AdminHelperWorker(ThreadedWorker):
    """Spawns (or confirms) the elevated helper process used to restore into
    a Windows profile other than the current user's — see services/elevation.py.

    Runs off the UI thread since it may block on the UAC prompt and on the
    helper's named pipe coming up.

    Example:
        w = AdminHelperWorker()
        w.finished.connect(on_started)
        w.start()
    """
    finished = pyqtSignal(bool)  # started_ok

    def run(self) -> None:
        try:
            from services.elevation import ensure_helper_started
            self.finished.emit(ensure_helper_started())
        except Exception as exc:
            logger.error('{"event":"admin_helper_worker_error","error":"%s"}', exc)
            self.finished.emit(False)


class AdminPrepareRestoreWorker(ThreadedWorker):
    """Recursively walks selected directories to compile restoration file list."""
    finished = pyqtSignal(list)  # list[MergedFile]

    def __init__(self, source: object, scope: str, profile_name: Optional[str] = None) -> None:
        super().__init__()
        self._source = source
        self._scope = scope
        self._profile_name = profile_name

    def run(self) -> None:
        try:
            from services.admin_backup_discovery import compile_admin_restore_files
            files = compile_admin_restore_files(self._source, self._scope, self._profile_name)
            self.finished.emit(files)
        except Exception as exc:
            logger.error('{"event":"prepare_restore_error","error":"%s"}', exc)
            self.error.emit(str(exc))
            self.finished.emit([])


class WorkerSignals(QObject):
    finished = pyqtSignal(object)  # AdminBackupSource
    progress = pyqtSignal(object)  # AdminBackupSource
    error = pyqtSignal(str)


class AdminSourceDetailRunnable(QRunnable):
    """Compute exact RAIZ/profile sizes for a single selected admin source in parallel.

    Uses QThreadPool and reports progressive updates via signals.
    """

    def __init__(self, source: object) -> None:
        super().__init__()
        self.source = source
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            from services.admin_backup_discovery import load_source_details
            detailed = load_source_details(self.source, progress_cb=self.signals.progress.emit)
            self.signals.finished.emit(detailed)
        except Exception as exc:
            logger.error('{"event":"source_detail_error","error":"%s"}', exc)
            self.signals.error.emit(str(exc))
            self.signals.finished.emit(self.source)
