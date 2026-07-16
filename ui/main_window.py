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

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMainWindow

from config import get_app_name
from services.backup_copier import CopyResult
from services.backup_discovery import BackupSource
from services.backup_merger import MergedFile, MergedFileSet, filter_files_by_selection
from ui.assets import STYLESHEET, asset_path
from ui.fade_stack import FadeStackWidget
from ui.telemetry import report_success, report_failure
from ui.views.welcome_view import WelcomeView
from ui.views.analysis_view import AnalysisView
from ui.views.confirm_view import ConfirmView
from ui.views.progress_view import ProgressView
from ui.views.summary_view import SummaryView
from ui.views.about_view import AboutView
from ui.views.admin_view import AdminView
from ui.views.admin_restore_view import AdminRestoreView
from ui.views.admin_create_backup_view import AdminCreateBackupView, AdminCreateBackupConfigView
from ui.workers import (
    DiscoverSourcesWorker,
    MergeSourcesWorker,
    CopyFilesWorker,
    CopySkippedWorker,
    BenchmarkWorker,
    AdminHelperWorker,
    CreateBackupWorker,
)
from ui.format_utils import format_bytes as _format_bytes

logger = logging.getLogger(__name__)

# View indices in the FadeStackWidget
_WELCOME = 0
_ANALYSIS = 1
_CONFIRM = 2
_PROGRESS = 3
_SUMMARY = 4
_ABOUT = 5
_ADMIN = 6
_ADMIN_RESTORE = 7
_ADMIN_CREATE_BACKUP = 8
_ADMIN_CREATE_BACKUP_CONFIG = 9



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
        self._skipped_copy_count = 0

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
        self._admin_restore = AdminRestoreView(self)
        self._admin_create_backup = AdminCreateBackupView(self)
        self._admin_create_backup_config = AdminCreateBackupConfigView(self)

        self._stack.add_view(self._welcome)
        self._stack.add_view(self._analysis)
        self._stack.add_view(self._confirm)
        self._stack.add_view(self._progress)
        self._stack.add_view(self._summary)
        self._stack.add_view(self._about)
        self._stack.add_view(self._admin)
        self._stack.add_view(self._admin_restore)
        self._stack.add_view(self._admin_create_backup)
        self._stack.add_view(self._admin_create_backup_config)

    def _connect_signals(self) -> None:
        """Wire view signals to navigation handlers.

        Example:
            self._connect_signals()
        """
        self._welcome.start_requested.connect(self._go_to_analysis)
        self._welcome.about_requested.connect(self._go_to_about)
        self._welcome.admin_mode_requested.connect(self._request_admin_mode)
        self._analysis.next_requested.connect(self._go_to_confirm)
        self._analysis.back_requested.connect(self._go_to_welcome)
        self._analysis.retry_requested.connect(self._retry_discovery)
        self._confirm.restore_requested.connect(self._start_restore)
        self._confirm.back_requested.connect(self._go_to_analysis_from_confirm)
        self._progress.cancel_requested.connect(self._cancel_restore)
        self._summary.copy_skipped_requested.connect(self._copy_skipped)
        self._summary.finish_requested.connect(self.close)
        self._summary.try_other_requested.connect(self._request_admin_mode)
        self._about.back_requested.connect(self._go_to_welcome)
        self._admin.back_requested.connect(self._go_to_welcome)
        self._admin.restore_requested.connect(self._start_admin_restore)
        self._admin.create_backup_requested.connect(self._start_admin_create_backup)
        self._admin_restore.back_requested.connect(self._go_to_admin_dashboard)
        self._admin_restore.next_requested.connect(self._on_admin_restore_prepared)
        self._admin_create_backup.back_requested.connect(self._go_to_admin_dashboard)
        self._admin_create_backup.continue_requested.connect(self._go_to_admin_create_backup_config)
        self._admin_create_backup_config.back_requested.connect(self._go_to_admin_create_backup)
        self._admin_create_backup_config.start_backup_requested.connect(self._start_backup_creation)


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
        self._report_discovery_result(sources)
        if self._stack.currentIndex() == _ANALYSIS:
            self._process_sources()

    def _on_discovery_error(self, error: str) -> None:
        """Handle discovery error by logging it.

        Example:
            self._on_discovery_error("error details")
        """
        logger.error('{"event":"discovery_error","error":"%s"}', error)

    def _report_discovery_result(self, sources: list) -> None:
        """Report discovery outcome — empty result is a real failure funnel step."""
        if not sources:
            report_failure("DISCOVERY_EMPTY", "no backup source found")
            return
        report_success("DISCOVERY_COMPLETE", {
            "source_count": len(sources),
            "network_count": sum(1 for s in sources if s.origin == "network"),
            "local_count": sum(1 for s in sources if s.origin == "local"),
            "total_bytes": sum(s.total_bytes for s in sources),
        })

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_welcome(self) -> None:
        """Navigate back to the welcome view.

        Example:
            self._go_to_welcome()
        """
        self._state.admin_mode = False
        self._state.sources.clear()
        self._state.merged = None
        self._stack.navigate_to(_WELCOME)
        self._start_background_discovery()

    def _request_admin_mode(self) -> None:
        """Gate entry to admin mode behind a Windows UAC prompt instead of
        the old in-app password: accepting it both proves the user has
        admin rights on this machine and starts the elevated helper process
        (see services/elevation.py) that every restore-to-another-profile
        during this session will reuse — so it's asked once, here.

        Example:
            self._request_admin_mode()
        """
        if getattr(self, "_admin_helper_worker", None) is not None:
            return
        worker = AdminHelperWorker()
        worker.finished.connect(self._on_admin_mode_elevation_result)
        self._admin_helper_worker = worker
        self._workers.append(worker)
        worker.start()

    def _on_admin_mode_elevation_result(self, started_ok: bool) -> None:
        """Enter the admin view on a successful UAC prompt, or report why not."""
        self._admin_helper_worker = None
        self._report_admin_mode_elevation(started_ok)
        if started_ok:
            self._stack.navigate_to(_ADMIN)
            return
        logger.warning('{"event":"admin_mode_elevation_failed"}')
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(
            self, "Modo admin",
            "Não foi possível habilitar o Modo admin: a elevação de privilégios "
            "foi cancelada ou falhou.",
            QMessageBox.Ok,
        )

    def _start_admin_restore(self) -> None:
        """Start the backup restoration flow in admin mode.

        Example:
            self._start_admin_restore()
        """
        self._state.admin_mode = True
        self._state.sources.clear()
        self._state.merged = None
        self._stack.navigate_to(_ADMIN_RESTORE)
        self._admin_restore.start_discovery()

    def _go_to_admin_dashboard(self) -> None:
        """Navigate back to the admin tool dashboard."""
        self._state.admin_mode = False
        self._stack.navigate_to(_ADMIN)

    def _start_admin_create_backup(self) -> None:
        """Start the backup creation flow in admin mode."""
        self._state.admin_mode = True
        self._stack.navigate_to(_ADMIN_CREATE_BACKUP)

    def _go_to_admin_create_backup_config(self, files: list[MergedFile], skip_media_exec: bool) -> None:
        """Navigate to configuration screen for backup creation."""
        self._admin_create_backup_config.setup(files, skip_media_exec)
        self._stack.navigate_to(_ADMIN_CREATE_BACKUP_CONFIG)

    def _go_to_admin_create_backup(self) -> None:
        """Navigate back to folder selection screen."""
        self._stack.navigate_to(_ADMIN_CREATE_BACKUP)

    def _on_admin_restore_prepared(self) -> None:
        """Handle transition after admin restore files are compiled."""
        merged = self._state.merged
        if merged:
            is_local = all(s.origin == "local" for s in self._state.sources) if self._state.sources else True
            self._confirm.populate(merged, True, is_local)
            self._start_background_benchmarks(merged)
            self._stack.navigate_to(_CONFIRM)


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
        if self._state.admin_mode:
            self._stack.navigate_to(_ADMIN_RESTORE)
        else:
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
        report_success("DISCOVERY_RETRY")
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
        self._report_merge_result(merged)
        if merged.files:
            self._analysis.set_resolved(merged, self._state.admin_mode)
            is_local = all(s.origin == "local" for s in self._state.sources) if self._state.sources else True
            self._confirm.populate(merged, self._state.admin_mode, is_local)
            self._start_background_benchmarks(merged)
        else:
            self._analysis.set_no_source()

    def _report_merge_result(self, merged: MergedFileSet) -> None:
        if merged.files:
            report_success("MERGE_COMPLETE", {
                "file_count": len(merged.files),
                "total_bytes": merged.total_bytes,
                "source_count": len(self._state.sources),
            })
        else:
            report_failure("MERGE_EMPTY", "merge produced no files")

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

        cut_mode = False
        if self._state.admin_mode and hasattr(self._confirm, "cut_checkbox"):
            is_local = all(s.origin == "local" for s in self._state.sources) if self._state.sources else True
            if is_local:
                cut_mode = self._confirm.cut_checkbox.isChecked()

        self._progress.reset()
        self._stack.navigate_to(_PROGRESS)

        self._copy_worker = CopyFilesWorker(files_to_copy, cut_mode=cut_mode)
        self._copy_worker.progress.connect(self._progress.update_progress)
        self._copy_worker.finished.connect(self._on_copy_finished)
        self._workers.append(self._copy_worker)
        self._copy_worker.start()

        self._report_restore_start(len(files_to_copy), cut_mode)

    def _filter_files_by_folders(
        self, selected_folders: list[str],
    ) -> list[MergedFile]:
        """Return only merged files whose dest_folder is selected."""
        if not self._state.merged:
            return []
        return filter_files_by_selection(self._state.merged.files, selected_folders)

    def _on_copy_finished(self, result: CopyResult) -> None:
        """Handle copy completion — navigate to summary."""
        self._state.copy_result = result
        self._summary.populate(result, self._state.admin_mode)
        self._stack.navigate_to(_SUMMARY)
        self._report_restore_result(result)

    def _cancel_restore(self) -> None:
        """Forward cancel request to the active copy worker."""
        if hasattr(self, "_copy_worker"):
            self._copy_worker.request_cancel()
        if hasattr(self, "_backup_worker"):
            self._backup_worker.request_cancel()

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

        self._skipped_copy_count = len(all_skipped)
        worker = CopySkippedWorker(all_skipped)
        worker.finished.connect(self._summary.on_skipped_copy_done)
        worker.finished.connect(self._report_copy_skipped_result)
        self._workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Telemetry helpers
    # ------------------------------------------------------------------

    def _report_admin_mode_elevation(self, started_ok: bool) -> None:
        if started_ok:
            report_success("ADMIN_MODE_ELEVATION")
        else:
            report_failure(
                "ADMIN_MODE_ELEVATION", "UAC prompt declined or helper failed to start",
            )

    def _report_restore_start(self, file_count: int, cut_mode: bool) -> None:
        report_success("RESTORE_START", {
            "file_count": file_count,
            "admin_mode": self._state.admin_mode,
            "cut_mode": cut_mode,
        })

    def _report_restore_result(self, result: CopyResult) -> None:
        details = {
            "files_copied": result.files_copied,
            "bytes_copied": result.bytes_copied,
            "skipped_count": len(result.skipped_files),
            "failed_count": len(result.failed_files),
            "cancelled": result.cancelled,
            "duration_seconds": result.duration_seconds,
            "admin_mode": self._state.admin_mode,
        }
        if result.success:
            report_success("RESTORE_COMPLETE", details)
        else:
            report_failure("RESTORE_FAILED", "copy failed or cancelled", details)

    def _report_copy_skipped_result(self, success: bool, _msg: str) -> None:
        details = {"file_count": self._skipped_copy_count}
        if success:
            report_success("COPY_SKIPPED_TO_DESKTOP", details)
        else:
            report_failure("COPY_SKIPPED_TO_DESKTOP", "failed to copy skipped files", details)

    def _start_backup_creation(self, files: list[MergedFile], dest_root: Path, skip_media_exec: bool) -> None:
        """Begin copying files to the backup target."""
        self._progress.reset()
        self._progress.title.setText("Criando backup dos arquivos")
        self._stack.navigate_to(_PROGRESS)

        self._backup_worker = CreateBackupWorker(files, dest_root, skip_media_exec)
        self._backup_worker.progress.connect(self._progress.update_progress)
        self._backup_worker.finished.connect(self._on_backup_creation_finished)
        self._workers.append(self._backup_worker)
        self._backup_worker.start()

        report_success("BACKUP_START", {
            "file_count": len(files),
            "dest_root": str(dest_root),
            "skip_media_exec": skip_media_exec,
        })

    def _on_backup_creation_finished(self, result: CopyResult) -> None:
        """Handle backup completion — navigate to summary."""
        # 1. We must configure SummaryView titles for backup!
        self._summary._files_card.update_content(
            title="ARQUIVOS SALVOS",
            value=f"{result.files_copied} arquivos",
            subtitle="Backup concluído",
        )
        self._summary._bytes_card.update_content(
            title="VOLUME DO BACKUP",
            value=_format_bytes(result.bytes_copied),
            subtitle="Tamanho total",
        )

        # 2. Update summary view text details for backup
        from ui.assets import RM_GREEN, RM_RED, RM_YELLOW
        n_issues = len(result.skipped_files) + len(result.failed_files)
        if result.cancelled:
            self._summary._set_header_lbl("BACKUP CANCELADO", RM_RED, "O backup foi cancelado pelo usuário.")
        elif result.files_copied == 0:
            self._summary._set_header_lbl("BACKUP FALHOU", RM_RED, "Nenhum arquivo pôde ser salvo.")
        elif n_issues:
            suffix = "arquivo pulado" if n_issues == 1 else "arquivos pulados"
            self._summary._set_header_lbl(
                "BACKUP PARCIAL", RM_YELLOW,
                f"{result.files_copied} arquivos salvos, {n_issues} {suffix}.",
            )
        else:
            self._summary._set_header_lbl("BACKUP CONCLUÍDO", RM_GREEN, "Todos os arquivos salvos com sucesso!")

        self._summary._set_skipped_section(result)
        self._summary._try_other_btn.setVisible(True)

        self._state.copy_result = result
        self._stack.navigate_to(_SUMMARY)

        # Telemetry/Logging
        details = {
            "files_copied": result.files_copied,
            "bytes_copied": result.bytes_copied,
            "skipped_count": len(result.skipped_files),
            "failed_count": len(result.failed_files),
            "cancelled": result.cancelled,
            "duration_seconds": result.duration_seconds,
        }
        if result.success:
            report_success("BACKUP_COMPLETE", details)
        else:
            report_failure("BACKUP_FAILED", "backup failed or cancelled", details)
