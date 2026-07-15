from __future__ import annotations

"""Unit tests for telemetry reporting: ui.telemetry helpers and the
event/detail enrichment added to MainWindow and AdminRestoreView.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PyQt5.QtWidgets import QApplication

from services.backup_copier import CopyResult
from services.backup_discovery import BackupSource
from services.backup_merger import MergedFileSet
from ui.main_window import MainWindow, SessionState
from ui.views.admin_restore_view import AdminRestoreView

app = QApplication.instance() or QApplication(sys.argv)


class FakeApiService:
    """Named fake standing in for ApiService — records calls, does no I/O."""

    def __init__(self) -> None:
        self.success_calls: list[tuple] = []
        self.failure_calls: list[tuple] = []

    async def report_success(self, event, details=None) -> None:
        self.success_calls.append((event, details))

    async def report_failure(self, event, error_msg, details=None) -> None:
        self.failure_calls.append((event, error_msg, details))


class FakeWorker:
    """Named fake standing in for GlobalAsyncWorker — runs coroutines inline."""

    def __init__(self, api_service) -> None:
        self.api_service = api_service

    def submit_task(self, coro) -> None:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


class TestTelemetryHelpers(unittest.TestCase):
    """ui.telemetry.report_success / report_failure delegate to the global worker."""

    def test_report_success_reaches_api_service(self) -> None:
        fake_api = FakeApiService()
        with patch("ui.telemetry.get_global_worker", return_value=FakeWorker(fake_api)):
            from ui.telemetry import report_success
            report_success("DISCOVERY_COMPLETE", {"source_count": 2})
        self.assertEqual(fake_api.success_calls, [("DISCOVERY_COMPLETE", {"source_count": 2})])

    def test_report_failure_reaches_api_service(self) -> None:
        fake_api = FakeApiService()
        with patch("ui.telemetry.get_global_worker", return_value=FakeWorker(fake_api)):
            from ui.telemetry import report_failure
            report_failure("MERGE_EMPTY", "merge produced no files")
        self.assertEqual(
            fake_api.failure_calls, [("MERGE_EMPTY", "merge produced no files", None)],
        )

    def test_no_report_when_api_service_unavailable(self) -> None:
        with patch("ui.telemetry.get_global_worker", return_value=FakeWorker(None)):
            from ui.telemetry import report_success
            report_success("APP_STARTUP")  # must not raise


def _make_window(admin_mode: bool = False) -> MainWindow:
    """MainWindow without __init__ — no Qt widgets, no background threads."""
    win = MainWindow.__new__(MainWindow)
    win._state = SessionState(admin_mode=admin_mode)
    win._skipped_copy_count = 0
    return win


class TestDiscoveryTelemetry(unittest.TestCase):
    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_empty_discovery_reports_failure(self, mock_failure, mock_success) -> None:
        win = _make_window()
        win._report_discovery_result([])
        mock_failure.assert_called_once_with("DISCOVERY_EMPTY", "no backup source found")
        mock_success.assert_not_called()

    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_discovery_reports_origin_breakdown(self, mock_failure, mock_success) -> None:
        win = _make_window()
        sources = [
            BackupSource(Path("//srv/net"), "network", "PMC_1", 100),
            BackupSource(Path("C:/local"), "local", "PMC_1", 50),
            BackupSource(Path("C:/local2"), "local", "PMC_1", 25),
        ]
        win._report_discovery_result(sources)
        mock_failure.assert_not_called()
        mock_success.assert_called_once_with("DISCOVERY_COMPLETE", {
            "source_count": 3, "network_count": 1, "local_count": 2, "total_bytes": 175,
        })


class TestMergeTelemetry(unittest.TestCase):
    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_empty_merge_reports_failure(self, mock_failure, mock_success) -> None:
        win = _make_window()
        merged = MergedFileSet(files=[], total_bytes=0, source_summary="")
        win._report_merge_result(merged)
        mock_failure.assert_called_once_with("MERGE_EMPTY", "merge produced no files")
        mock_success.assert_not_called()

    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_on_merge_finished_empty_calls_set_no_source(self, mock_failure, mock_success) -> None:
        win = _make_window()
        win._analysis = MagicMock()
        merged = MergedFileSet(files=[], total_bytes=0, source_summary="")
        win._on_merge_finished(merged)
        win._analysis.set_no_source.assert_called_once()
        mock_failure.assert_called_once_with("MERGE_EMPTY", "merge produced no files")


class TestRestoreTelemetry(unittest.TestCase):
    @patch("ui.main_window.report_success")
    def test_restore_start_includes_admin_and_cut_mode(self, mock_success) -> None:
        win = _make_window(admin_mode=True)
        win._report_restore_start(42, cut_mode=True)
        mock_success.assert_called_once_with("RESTORE_START", {
            "file_count": 42, "admin_mode": True, "cut_mode": True,
        })

    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_restore_result_success_includes_duration(self, mock_failure, mock_success) -> None:
        win = _make_window()
        result = CopyResult(success=True, files_copied=5, bytes_copied=1000, duration_seconds=7)
        win._report_restore_result(result)
        mock_failure.assert_not_called()
        mock_success.assert_called_once()
        event, details = mock_success.call_args[0]
        self.assertEqual(event, "RESTORE_COMPLETE")
        self.assertEqual(details["duration_seconds"], 7)
        self.assertIs(details["admin_mode"], False)

    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_restore_result_failure_reports_cancelled(self, mock_failure, mock_success) -> None:
        win = _make_window()
        result = CopyResult(success=False, files_copied=0, bytes_copied=0, cancelled=True)
        win._report_restore_result(result)
        mock_success.assert_not_called()
        mock_failure.assert_called_once()
        event, error_msg, details = mock_failure.call_args[0]
        self.assertEqual(event, "RESTORE_FAILED")
        self.assertTrue(details["cancelled"])


class TestCopySkippedTelemetry(unittest.TestCase):
    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_reports_success_with_count(self, mock_failure, mock_success) -> None:
        win = _make_window()
        win._skipped_copy_count = 3
        win._report_copy_skipped_result(True, "C:/Desktop/x")
        mock_failure.assert_not_called()
        mock_success.assert_called_once_with("COPY_SKIPPED_TO_DESKTOP", {"file_count": 3})

    @patch("ui.main_window.report_success")
    @patch("ui.main_window.report_failure")
    def test_reports_failure_with_count(self, mock_failure, mock_success) -> None:
        win = _make_window()
        win._skipped_copy_count = 2
        win._report_copy_skipped_result(False, "boom")
        mock_success.assert_not_called()
        mock_failure.assert_called_once_with(
            "COPY_SKIPPED_TO_DESKTOP", "failed to copy skipped files", {"file_count": 2},
        )


class TestAdminSearchTelemetry(unittest.TestCase):
    @patch("ui.views.admin_restore_view.report_success")
    @patch("ui.views.admin_restore_view.report_failure")
    def test_zero_results_reports_failure(self, mock_failure, mock_success) -> None:
        view = AdminRestoreView.__new__(AdminRestoreView)
        view.sources = []
        view._current_query = "14029"
        view._report_search_result()
        mock_success.assert_not_called()
        mock_failure.assert_called_once_with(
            "ADMIN_SEARCH", "no results", {"result_count": 0, "has_query": True},
        )

    @patch("ui.views.admin_restore_view.report_success")
    @patch("ui.views.admin_restore_view.report_failure")
    def test_results_report_success(self, mock_failure, mock_success) -> None:
        view = AdminRestoreView.__new__(AdminRestoreView)
        view.sources = [object(), object()]
        view._current_query = None
        view._report_search_result()
        mock_failure.assert_not_called()
        mock_success.assert_called_once_with(
            "ADMIN_SEARCH", {"result_count": 2, "has_query": False},
        )


class TestAdminPrepareTelemetry(unittest.TestCase):
    @patch("ui.views.admin_restore_view.report_success")
    def test_reports_counts_not_profile_names(self, mock_success) -> None:
        """Scope must be reported by count, not name — names could identify other users."""
        view = AdminRestoreView.__new__(AdminRestoreView)
        view._processing_raiz_sel = True
        view._processing_sel_profiles = {"14029", "14030"}
        view._report_prepare_result(files=[1, 2, 3], total_bytes=999)
        mock_success.assert_called_once_with("ADMIN_RESTORE_PREPARED", {
            "file_count": 3, "total_bytes": 999,
            "raiz_selected": True, "profile_count": 2,
        })


if __name__ == "__main__":
    unittest.main()
