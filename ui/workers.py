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

from PyQt5.QtCore import QThread, pyqtSignal, QObject

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
    ) -> None:
        super().__init__()
        self._files = files
        self._cancel = Event()
        self._retry_cfg = retry_cfg or get_copy_retry_config()

    def run(self) -> None:
        try:
            from services.backup_copier import copy_merged_files
            result = copy_merged_files(
                self._files,
                progress_cb=self._on_progress,
                cancel_event=self._cancel,
                retry_cfg=self._retry_cfg,
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
        from services.backup_copier import run_write_benchmark
        local_speed = run_write_benchmark(self._local_path)
        net_speed = 0
        if self._network_path:
            net_speed = run_write_benchmark(self._network_path)
        self.finished.emit(float(local_speed), float(net_speed))
