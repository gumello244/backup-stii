from __future__ import annotations

"""Remos MainWindow — orchestrates the 5-screen guided flow.

Owns the FadeStackWidget, SessionState, and all inter-view wiring.
Background workers are started here and results flow through signals.

Example:
    window = MainWindow()
    window.show()
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow, QWidget

from config import get_app_name
from services.backup_copier import CopyResult, SkippedFile
from services.backup_discovery import BackupSource
from services.backup_merger import MergedFile, MergedFileSet
from ui.assets import STYLESHEET, asset_path
from ui.fade_stack import FadeStackWidget
from ui.views.welcome_view import WelcomeView
from ui.views.analysis_view import AnalysisView
from ui.views.confirm_view import ConfirmView
from ui.views.progress_view import ProgressView
from ui.views.summary_view import SummaryView
from ui.views.about_view import AboutView
from ui.views.admin_view import AdminView
from ui.workers import (
    DiscoverSourcesWorker,
    MergeSourcesWorker,
    CopyFilesWorker,
    CopySkippedWorker,
    BenchmarkWorker,
    get_global_worker,
)

logger = logging.getLogger(__name__)

# View indices in the FadeStackWidget
_WELCOME = 0
_ANALYSIS = 1
_CONFIRM = 2
_PROGRESS = 3
_SUMMARY = 4
_ABOUT = 5
_ADMIN = 6



@dataclass
class SessionState:
    """Shared mutable state across all views.

    Example:
        state = SessionState()
        state.sources = discovered_sources
    """
    user_login: str = ""
    machine_id: str = ""
    admin_mode: bool = False
    sources: list[BackupSource] = field(default_factory=list)
    merged: Optional[MergedFileSet] = None
    selected_folders: list[str] = field(default_factory=list)
    copy_result: Optional[CopyResult] = None


class MainWindow(QMainWindow):
    """660x440 fixed-size window housing the Remos guided flow.

    Example:
        win = MainWindow()
        win.show()
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(get_app_name())
        self.setFixedSize(660, 440)
        self.setStyleSheet(STYLESHEET)
        self._set_icon()

        self._state = SessionState()
        self._workers: list[object] = []  # prevent GC

        self._init_views()
        self._connect_signals()
        self._start_background_discovery()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _set_icon(self) -> None:
        icon_file = asset_path("icon.ico")
        self.setWindowIcon(QIcon(icon_file))

    def _init_views(self) -> None:
        """Create all views and add them to the fade stack.

        Example:
            self._init_views()
        """
        self._stack = FadeStackWidget(self)
        self.setCentralWidget(self._stack)

        self._welcome = WelcomeView(self)
        self._analysis = AnalysisView(self)
        self._confirm = ConfirmView(self)
        self._progress = ProgressView(self)
        self._summary = SummaryView(self)
        self._about = AboutView(self)
        self._admin = AdminView(self)

        self._stack.add_view(self._welcome)
        self._stack.add_view(self._analysis)
        self._stack.add_view(self._confirm)
        self._stack.add_view(self._progress)
        self._stack.add_view(self._summary)
        self._stack.add_view(self._about)
        self._stack.add_view(self._admin)

    def _connect_signals(self) -> None:
        """Wire view signals to navigation handlers.

        Example:
            self._connect_signals()
        """
        self._welcome.start_requested.connect(self._go_to_analysis)
        self._welcome.about_requested.connect(self._go_to_about)
        self._welcome.admin_mode_unlocked.connect(self._go_to_admin)
        self._analysis.next_requested.connect(self._go_to_confirm)
        self._analysis.back_requested.connect(self._go_to_welcome)
        self._analysis.retry_requested.connect(self._retry_discovery)
        self._confirm.restore_requested.connect(self._start_restore)
        self._confirm.back_requested.connect(self._go_to_analysis_from_confirm)
        self._progress.cancel_requested.connect(self._cancel_restore)
        self._summary.copy_skipped_requested.connect(self._copy_skipped)
        self._summary.finish_requested.connect(self.close)
        self._about.back_requested.connect(self._go_to_welcome)
        self._admin.back_requested.connect(self._go_to_welcome)
        self._admin.restore_requested.connect(self._start_admin_restore)


    # ------------------------------------------------------------------
    # Background discovery (starts on construction)
    # ------------------------------------------------------------------

    def _start_background_discovery(self) -> None:
        """Kick off source discovery while the Welcome screen is shown.

        Example:
            self._start_background_discovery()
        """
        self._discovery_worker = DiscoverSourcesWorker(self._state.admin_mode)
        self._discovery_worker.finished.connect(self._on_sources_discovered)
        self._discovery_worker.error.connect(self._on_discovery_error)
        self._workers.append(self._discovery_worker)
        self._discovery_worker.start()

    def _on_sources_discovered(self, sources: list) -> None:
        """Handle finished discovery — store results, update analysis.

        Example:
            self._on_sources_discovered(sources)
        """
        self._state.sources = sources
        logger.info(
            '{"event":"sources_discovered","count":%d}', len(sources),
        )
        if self._stack.currentIndex() == _ANALYSIS:
            self._process_sources()

    def _on_discovery_error(self, error: str) -> None:
        """Handle discovery error by logging it.

        Example:
            self._on_discovery_error("error details")
        """
        logger.error('{"event":"discovery_error","error":"%s"}', error)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_welcome(self) -> None:
        """Navigate back to the welcome view.

        Example:
            self._go_to_welcome()
        """
        self._state.admin_mode = False
        self._stack.navigate_to(_WELCOME)

    def _go_to_admin(self) -> None:
        """Navigate to the admin view.

        Example:
            self._go_to_admin()
        """
        self._stack.navigate_to(_ADMIN)

    def _start_admin_restore(self) -> None:
        """Start the backup restoration flow in admin mode.

        Example:
            self._start_admin_restore()
        """
        self._state.admin_mode = True
        self._state.sources.clear()
        self._state.merged = None
        self._stack.navigate_to(_ANALYSIS)
        self._analysis.set_discovering()
        self._start_background_discovery()


    def _go_to_about(self) -> None:
        """Navigate to the about view.

        Example:
            self._go_to_about()
        """
        self._stack.navigate_to(_ABOUT)

    def _go_to_analysis(self) -> None:
        """Navigate to the analysis view.

        Example:
            self._go_to_analysis()
        """
        self._stack.navigate_to(_ANALYSIS)
        if self._state.sources:
            self._process_sources()
            return
        self._analysis.set_discovering()

    def _go_to_analysis_from_confirm(self) -> None:
        """Back from confirm — re-show resolved state.

        Example:
            self._go_to_analysis_from_confirm()
        """
        self._stack.navigate_to(_ANALYSIS)
        if self._state.merged:
            self._analysis.set_resolved(self._state.merged, self._state.admin_mode)

    def _go_to_confirm(self) -> None:
        """Navigate to the confirmation view.

        Example:
            self._go_to_confirm()
        """
        self._stack.navigate_to(_CONFIRM)

    def _retry_discovery(self) -> None:
        """User clicked "Tentar novamente" — re-run discovery.

        Example:
            self._retry_discovery()
        """
        self._state.sources.clear()
        self._state.merged = None
        self._analysis.set_discovering()
        self._start_background_discovery()

    # ------------------------------------------------------------------
    # Source processing (merge logic)
    # ------------------------------------------------------------------

    def _process_sources(self) -> None:
        """Decide how to handle discovered sources."""
        if not self._state.sources:
            self._analysis.set_no_source()
            return

        if len(self._state.sources) == 1:
            self._start_merge(self._state.sources)
            return

        # Multiple sources — run full merge
        self._analysis.set_merging()
        self._start_merge(self._state.sources)

    def _start_merge(self, sources: list[BackupSource]) -> None:
        """Run the merge worker in background."""
        self._analysis.set_merging()
        worker = MergeSourcesWorker(sources, self._state.admin_mode)
        worker.finished.connect(self._on_merge_finished)
        self._workers.append(worker)
        worker.start()

    def _on_merge_finished(self, merged: MergedFileSet) -> None:
        """Handle merge completion."""
        self._state.merged = merged
        if merged.files:
            self._analysis.set_resolved(merged, self._state.admin_mode)
            self._confirm.populate(merged)
            self._start_background_benchmarks(merged)
        else:
            self._analysis.set_no_source()

    def _start_background_benchmarks(self, merged: MergedFileSet) -> None:
        """Launch background benchmark thread once merge is finished."""
        net_file = next(
            (f for f in merged.files if f.source_path.drive.startswith("\\\\")),
            None,
        )
        net_path = net_file.source_path.parent if net_file else None
        worker = BenchmarkWorker(Path.home(), net_path)
        worker.finished.connect(self._on_benchmarks_finished)
        self._workers.append(worker)
        worker.start()

    def _on_benchmarks_finished(self, local_speed: float, network_speed: float) -> None:
        """Handle completion of background speed benchmarks."""
        self._confirm.set_benchmarked_speeds(local_speed, network_speed)

    # ------------------------------------------------------------------
    # Restore (copy)
    # ------------------------------------------------------------------

    def _start_restore(self, selected_folders: list) -> None:
        """Begin copying files for the selected folders."""
        self._state.selected_folders = selected_folders
        files_to_copy = self._filter_files_by_folders(selected_folders)

        self._progress.reset()
        self._stack.navigate_to(_PROGRESS)

        self._copy_worker = CopyFilesWorker(files_to_copy)
        self._copy_worker.progress.connect(self._progress.update_progress)
        self._copy_worker.finished.connect(self._on_copy_finished)
        self._workers.append(self._copy_worker)
        self._copy_worker.start()

        self._report_restore_start(len(files_to_copy))

    def _filter_files_by_folders(
        self, selected_folders: list[str],
    ) -> list[MergedFile]:
        """Return only merged files whose dest_folder is selected."""
        if not self._state.merged:
            return []
        folder_set = set(selected_folders)
        return [
            f for f in self._state.merged.files
            if f.dest_folder in folder_set
        ]

    def _on_copy_finished(self, result: CopyResult) -> None:
        """Handle copy completion — navigate to summary."""
        self._state.copy_result = result
        self._summary.populate(result)
        self._stack.navigate_to(_SUMMARY)
        self._report_restore_result(result)

    def _cancel_restore(self) -> None:
        """Forward cancel request to the active copy worker."""
        if hasattr(self, "_copy_worker"):
            self._copy_worker.request_cancel()

    # ------------------------------------------------------------------
    # Skipped files copy
    # ------------------------------------------------------------------

    def _copy_skipped(self) -> None:
        """Copy conflicting files to a Desktop folder."""
        if not self._state.copy_result:
            return
        all_skipped = (
            self._state.copy_result.skipped_files
            + self._state.copy_result.failed_files
        )
        if not all_skipped:
            return

        worker = CopySkippedWorker(all_skipped)
        worker.finished.connect(self._summary.on_skipped_copy_done)
        self._workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Telemetry helpers
    # ------------------------------------------------------------------

    def _report_restore_start(self, file_count: int) -> None:
        w = get_global_worker()
        if w.api_service:
            w.submit_task(w.api_service.report_success(
                "RESTORE_START", {"file_count": file_count},
            ))

    def _report_restore_result(self, result: CopyResult) -> None:
        w = get_global_worker()
        if not w.api_service:
            return
        details = {
            "files_copied": result.files_copied,
            "bytes_copied": result.bytes_copied,
            "skipped_count": len(result.skipped_files),
            "failed_count": len(result.failed_files),
            "cancelled": result.cancelled,
        }
        if result.success:
            w.submit_task(w.api_service.report_success(
                "RESTORE_COMPLETE", details,
            ))
        else:
            w.submit_task(w.api_service.report_failure(
                "RESTORE_FAILED", "copy failed or cancelled", details,
            ))
