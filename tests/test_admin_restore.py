from __future__ import annotations

"""Unit tests for Remos Admin Mode backup restoration logic and UI components."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PyQt5 import sip
from PyQt5.QtCore import QThreadPool
from PyQt5.QtWidgets import QApplication

from services.backup_copier import resolve_dest_path
from services.admin_backup_discovery import (
    PENDING_STATS,
    AdminBackupSource,
    RaizDetail,
    UserProfileDetail,
    compile_admin_restore_files,
)
from ui.views.admin_restore_view import AdminRestoreView, _source_sort_key
from ui.views.admin_restore_cards import SourceCard, RaizDetailCard, ProfileRow
from ui.workers import AdminDiscoverSourcesWorker

app = QApplication.instance() or QApplication(sys.argv)


def _join_worker(worker: object, timeout_ms: int = 5000) -> None:
    """Wait for a QThread test worker to finish without QThread.terminate().

    terminate() kills the OS thread at an arbitrary bytecode instruction. If
    that instant happens to fall inside a logger.error() call (see
    AdminPrepareRestoreWorker.run()'s except-branch), the thread dies while
    holding Python's process-wide logging module lock — every logging call
    made afterwards, from any thread or test module, then blocks forever.
    That is what previously made `unittest discover` hang partway through
    tests/test_api_service.py: it runs after this module and its very first
    failure-path test calls logger.error(). Waiting for natural completion
    (these workers run against a fake path and fail almost immediately)
    avoids killing the thread mid-log-call.
    """
    worker.wait(timeout_ms)


def tearDownModule() -> None:
    """Drain QThreadPool.globalInstance() and flush queued Qt events.

    AdminRestoreView._on_source_card_clicked() can submit an
    AdminSourceDetailRunnable to the process-wide QThreadPool. Those pooled
    worker threads run independently of any Qt event loop and outlive the
    test that spawned them, so a later test/module sharing this process can
    stall waiting on the pool (or on stale queued signal deliveries) unless
    we explicitly wait for pending work and pump the event queue here.
    """
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(3):
        app.processEvents()


class TestAdminRestorePaths(unittest.TestCase):
    """Verify that resolve_dest_path works correctly in admin mode settings."""

    def test_resolve_dest_path_raiz(self) -> None:
        """Verify RAIZ folder files resolve to C:\\ drive root."""
        dest = resolve_dest_path("RAIZ", "db.sqlite")
        self.assertEqual(dest, Path("C:\\db.sqlite"))

    def test_resolve_dest_path_custom_profile(self) -> None:
        """Verify other user profiles resolve to C:\\Users\\<profile>\\<folder>."""
        dest = resolve_dest_path("Desktop", "notes.txt", "12345")
        self.assertEqual(dest, Path("C:\\Users\\12345\\Desktop\\notes.txt"))

    def test_resolve_dest_path_default_profile(self) -> None:
        """Verify current profile fallback is respected if no target_profile is specified."""
        dest = resolve_dest_path("Desktop", "notes.txt", None)
        self.assertEqual(dest, Path.home() / "Desktop" / "notes.txt")


class TestAdminRestoreCompilation(unittest.TestCase):
    """Test compile_admin_restore_files under various scopes."""

    @patch("services.admin_backup_discovery.Path.is_dir", return_value=True)
    @patch("services.admin_backup_discovery.os.scandir")
    def test_compile_all_scope(self, mock_scandir: MagicMock, mock_is_dir: MagicMock) -> None:
        """Verify compiling entire source retrieves files from both RAIZ and profiles."""
        source = AdminBackupSource(
            path=Path("C:/OS_5_PMC_600259"),
            name="OS_5_PMC_600259",
            origin="network",
            machine_id="600259",
            total_bytes=1000,
            raiz=RaizDetail(size_bytes=400, file_count=1, dir_count=1, path=Path("C:/OS_5_PMC_600259/RAIZ")),
            profiles=[
                UserProfileDetail(
                    name="12345",
                    size_bytes=600,
                    modified_time=1719100000.0,
                    path=Path("C:/OS_5_PMC_600259/USUARIOS/12345")
                )
            ]
        )

        mock_entry_raiz = MagicMock()
        mock_entry_raiz.name = "raiz_db.sqlite"
        mock_entry_raiz.path = "C:/OS_5_PMC_600259/RAIZ/raiz_db.sqlite"
        mock_entry_raiz.is_file.return_value = True
        mock_entry_raiz.is_dir.return_value = False
        mock_entry_raiz.is_symlink.return_value = False
        mock_entry_raiz.stat.return_value.st_size = 400
        mock_entry_raiz.stat.return_value.st_mtime = 1719100000.0

        mock_entry_desktop = MagicMock()
        mock_entry_desktop.name = "Desktop"
        mock_entry_desktop.path = "C:/OS_5_PMC_600259/USUARIOS/12345/Desktop"
        mock_entry_desktop.is_file.return_value = False
        mock_entry_desktop.is_dir.return_value = True
        mock_entry_desktop.is_symlink.return_value = False

        mock_entry_user_file = MagicMock()
        mock_entry_user_file.name = "notes.txt"
        mock_entry_user_file.path = "C:/OS_5_PMC_600259/USUARIOS/12345/Desktop/notes.txt"
        mock_entry_user_file.is_file.return_value = True
        mock_entry_user_file.is_dir.return_value = False
        mock_entry_user_file.is_symlink.return_value = False
        mock_entry_user_file.stat.return_value.st_size = 600
        mock_entry_user_file.stat.return_value.st_mtime = 1719100000.0

        def scandir_side_effect(path):
            path_str = str(path).replace("\\", "/")
            if path_str.endswith("/RAIZ"):
                return [mock_entry_raiz]
            elif path_str.endswith("/USUARIOS/12345") or path_str.endswith("/USUARIOS"):
                # In _scan_profile_files we scan usuarios_dir, which yields the folder_entry "12345"
                # Wait, under USUARIOS we scan and it yields subdirectories
                if path_str.endswith("/USUARIOS"):
                    # We need a mock_entry_user folder
                    mock_entry_user = MagicMock()
                    mock_entry_user.name = "12345"
                    mock_entry_user.path = "C:/OS_5_PMC_600259/USUARIOS/12345"
                    mock_entry_user.is_file.return_value = False
                    mock_entry_user.is_dir.return_value = True
                    mock_entry_user.is_symlink.return_value = False
                    return [mock_entry_user]
                return [mock_entry_desktop]
            elif path_str.endswith("/USUARIOS/12345/Desktop"):
                return [mock_entry_user_file]
            return []

        class MockScandirContext:
            def __init__(self, entries):
                self.entries = entries
            def __enter__(self):
                return self.entries
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_scandir.side_effect = lambda path: MockScandirContext(scandir_side_effect(path))

        with patch("services.admin_backup_discovery.detect_user_login", return_value="14029"):
            files = compile_admin_restore_files(source, "all")
            self.assertEqual(len(files), 2)
            self.assertEqual(files[0].dest_folder, "RAIZ")
            self.assertEqual(files[1].target_profile, "12345")


class TestAdminWorkers(unittest.TestCase):
    """Test background workers emit correctly."""

    @patch("services.admin_backup_discovery.scan_admin_backups")
    def test_discover_worker(self, mock_scan: MagicMock) -> None:
        """Verify AdminDiscoverSourcesWorker emits source_found and finishes."""
        mock_source = AdminBackupSource(
            path=Path("C:/OS_5_PMC_600259"), name="OS_5_PMC_600259", origin="local",
            machine_id="600259", total_bytes=10, raiz=None, profiles=[]
        )
        mock_scan.return_value = [mock_source]

        worker = AdminDiscoverSourcesWorker()
        found_sources = []
        finished_emitted = False

        worker.source_found.connect(found_sources.append)
        worker.finished.connect(lambda: setattr(worker, "_finished", True))
        
        worker.run()
        self.assertEqual(len(found_sources), 1)
        self.assertEqual(found_sources[0].name, "OS_5_PMC_600259")


class TestSourceSortKey(unittest.TestCase):
    """_source_sort_key() must never collapse to 0.0 just because no profile
    has a real modified_time — it should fall back to the RAIZ or source
    folder's own filesystem mtime so newest-first sorting stays meaningful."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def _touch(self, path: Path, mtime: float) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        os.utime(path, (mtime, mtime))
        return path

    def test_uses_profile_modified_time_when_available(self) -> None:
        profile = UserProfileDetail(
            name="joao", size_bytes=1, modified_time=1_700_000_000.0, path=Path("P"),
        )
        src = AdminBackupSource(
            path=self._touch(self.tmp, 1_000_000_000.0), name="OS_5", origin="local",
            machine_id="", total_bytes=1, raiz=None, profiles=[profile],
        )
        self.assertEqual(_source_sort_key(src), 1_700_000_000.0)

    def test_falls_back_to_raiz_path_mtime_when_no_profile_times(self) -> None:
        raiz_path = self._touch(self.tmp / "RAIZ", 1_800_000_000.0)
        os.utime(self.tmp, (1_000_000_000.0, 1_000_000_000.0))
        src = AdminBackupSource(
            path=self.tmp, name="OS_5", origin="local", machine_id="", total_bytes=1,
            raiz=RaizDetail(size_bytes=0, file_count=1, dir_count=0, path=raiz_path),
            profiles=[],
        )
        self.assertEqual(_source_sort_key(src), raiz_path.stat().st_mtime)

    def test_falls_back_to_source_path_mtime_when_no_profiles_or_raiz(self) -> None:
        self._touch(self.tmp, 1_650_000_000.0)
        src = AdminBackupSource(
            path=self.tmp, name="OS_5", origin="local", machine_id="", total_bytes=1,
            raiz=None, profiles=[],
        )
        self.assertEqual(_source_sort_key(src), self.tmp.stat().st_mtime)

    def test_missing_path_does_not_raise(self) -> None:
        src = AdminBackupSource(
            path=self.tmp / "does-not-exist", name="OS_5", origin="local",
            machine_id="", total_bytes=1, raiz=None, profiles=[],
        )
        self.assertEqual(_source_sort_key(src), 0.0)


class TestAdminRestoreView(unittest.TestCase):
    """Test AdminRestoreView layout, selection model, and button labelling."""

    def _make_source(self, raiz: bool = True, profiles: list | None = None) -> AdminBackupSource:
        raiz_detail = (
            RaizDetail(size_bytes=100, file_count=1, dir_count=0, path=Path("P/RAIZ"))
            if raiz else None
        )
        profs = profiles or [UserProfileDetail(name="alice", size_bytes=500, modified_time=1.0, path=Path("P"))]
        return AdminBackupSource(
            path=Path("C:/OS_5_PMC_600259"), name="OS_5_PMC_600259", origin="local",
            machine_id="600259", total_bytes=600, raiz=raiz_detail, profiles=profs,
        )

    def test_view_elements_exist(self) -> None:
        """Verify key components are instantiated."""
        view = AdminRestoreView()
        self.assertIsNotNone(view.search_input)
        self.assertIsNotNone(view.search_btn)
        self.assertIsNotNone(view.current_user_btn)
        self.assertIsNotNone(view.raiz_card)
        self.assertIsNotNone(view._next_btn)

    @patch("ui.views.admin_restore_view.AdminDiscoverSourcesWorker")
    def test_start_discovery_sets_last_query_placeholder(self, mock_worker: MagicMock) -> None:
        """Submitted queries must leave the field empty and surface the query as a placeholder."""
        mock_worker.return_value.source_found = MagicMock()
        mock_worker.return_value.stage_changed = MagicMock()
        mock_worker.return_value.finished = MagicMock()

        view = AdminRestoreView()
        view.search_input.setText("old query")

        view.start_discovery("600259")

        self.assertEqual(view.search_input.text(), "")
        self.assertEqual(view.search_input.placeholderText(), 'Última busca: 600259')

    @patch("ui.views.admin_restore_view.AdminDiscoverSourcesWorker")
    def test_new_search_requests_previous_worker_cancel(self, mock_worker: MagicMock) -> None:
        """Starting a new search while a scan is active must ask the old worker to stop."""
        mock_worker.return_value.source_found = MagicMock()
        mock_worker.return_value.stage_changed = MagicMock()
        mock_worker.return_value.finished = MagicMock()
        mock_worker.return_value.start = MagicMock()

        view = AdminRestoreView()
        old_worker = MagicMock()
        old_worker.request_cancel = MagicMock()
        old_worker.source_found = MagicMock()
        old_worker.stage_changed = MagicMock()
        old_worker.finished = MagicMock()
        view.worker = old_worker

        view.start_discovery("600259")

        old_worker.request_cancel.assert_called_once()
        mock_worker.assert_called_once_with("600259")

    @patch("ui.views.admin_restore_view.AdminDiscoverSourcesWorker")
    def test_start_discovery_without_query_restores_default_placeholder(self, mock_worker: MagicMock) -> None:
        """Returning to the tool without a search must clear the field completely."""
        mock_worker.return_value.source_found = MagicMock()
        mock_worker.return_value.stage_changed = MagicMock()
        mock_worker.return_value.finished = MagicMock()

        view = AdminRestoreView()
        view.search_input.setText("prefilled")

        view.start_discovery()

        self.assertEqual(view.search_input.text(), "")
        self.assertEqual(view.search_input.placeholderText(), "Login, hostname, OS")

    @patch("ui.views.admin_restore_view.detect_user_login", return_value="14029")
    @patch.object(AdminRestoreView, "start_discovery")
    def test_current_user_button_triggers_current_login_search(
        self, mock_start_discovery: MagicMock, mock_detect_user_login: MagicMock,
    ) -> None:
        """The current-user shortcut should search with the detected login."""
        view = AdminRestoreView()

        view._on_current_user_clicked()

        mock_detect_user_login.assert_called_once()
        mock_start_discovery.assert_called_once_with("14029")

    def test_searching_page_shown_initially(self) -> None:
        """Verify the stacked widget starts on the searching page (index 0)."""
        view = AdminRestoreView()
        self.assertEqual(view._stack.currentIndex(), 0)

    def test_right_placeholder_hidden_after_source_selected(self) -> None:
        """Verify placeholder disappears and right panel appears on source click."""
        view = AdminRestoreView()
        self.assertFalse(view._right_placeholder.isHidden())
        view._on_source_card_clicked(self._make_source())
        self.assertTrue(view._right_placeholder.isHidden())
        self.assertFalse(view._right_widget.isHidden())

    def test_source_click_enables_next_full_restore(self) -> None:
        """Clicking source with no sub-selection shows 'Recuperar tudo'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source())
        self.assertTrue(view._next_btn.isEnabled())
        self.assertEqual(view._next_btn.text(), "Recuperar tudo")

    def test_raiz_card_hidden_when_no_raiz(self) -> None:
        """RAIZ card must not appear when source has no RAIZ data."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(raiz=False))
        self.assertTrue(view.raiz_card.isHidden())

    def test_raiz_toggle_updates_label(self) -> None:
        """Toggling RAIZ card should update button to 'Recuperar raiz'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(profiles=[]))
        view._on_raiz_toggled()
        self.assertEqual(view._next_btn.text(), "Recuperar raiz")

    def test_profile_toggle_updates_label(self) -> None:
        """Toggling one profile should show the singular recovery label."""
        view = AdminRestoreView()
        profile = UserProfileDetail(name="joao", size_bytes=200, modified_time=1.0, path=Path("P"))
        view._on_source_card_clicked(self._make_source(raiz=False, profiles=[profile]))
        view._on_profile_toggled(profile)
        self.assertEqual(view._next_btn.text(), "Recuperar usuário")

    def test_multi_profile_toggle_updates_label(self) -> None:
        """Selecting two profiles should collapse to the plural recovery label."""
        view = AdminRestoreView()
        p1 = UserProfileDetail(name="alice", size_bytes=200, modified_time=2.0, path=Path("P"))
        p2 = UserProfileDetail(name="bob", size_bytes=300, modified_time=1.0, path=Path("Q"))
        view._on_source_card_clicked(self._make_source(raiz=False, profiles=[p1, p2]))
        view._on_profile_toggled(p1)
        view._on_profile_toggled(p2)
        self.assertEqual(view._next_btn.text(), "Recuperar usuários")

    def test_raiz_plus_profile_combined_label(self) -> None:
        """RAIZ plus a single profile should use the combined recovery label."""
        view = AdminRestoreView()
        profile = UserProfileDetail(name="carol", size_bytes=400, modified_time=1.0, path=Path("P"))
        view._on_source_card_clicked(self._make_source(profiles=[profile]))
        view._on_raiz_toggled()
        view._on_profile_toggled(profile)
        self.assertEqual(view._next_btn.text(), "Recuperar raiz e usuário")

    def test_raiz_plus_multiple_profiles_combined_label(self) -> None:
        """RAIZ plus multiple profiles should use the combined plural recovery label."""
        view = AdminRestoreView()
        p1 = UserProfileDetail(name="carol", size_bytes=400, modified_time=1.0, path=Path("P"))
        p2 = UserProfileDetail(name="dan", size_bytes=200, modified_time=1.0, path=Path("Q"))
        view._on_source_card_clicked(self._make_source(profiles=[p1, p2]))
        view._on_raiz_toggled()
        view._on_profile_toggled(p1)
        view._on_profile_toggled(p2)
        self.assertEqual(view._next_btn.text(), "Recuperar raiz e usuários")

    def test_second_raiz_toggle_deselects(self) -> None:
        """Toggling RAIZ twice should deselect it and fall back to 'Recuperar tudo'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(profiles=[]))
        view._on_raiz_toggled()  # select
        view._on_raiz_toggled()  # deselect
        self.assertEqual(view._next_btn.text(), "Recuperar tudo")

    def test_next_clicked_starts_processing_and_blocks_ui(self) -> None:
        """Verify that clicking next/continue disables search controls, changes back to Cancelar, and sets process state."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source())
        
        # Trigger preparation
        view._on_next_clicked()
        
        self.assertFalse(view.search_btn.isEnabled())
        self.assertFalse(view.current_user_btn.isEnabled())
        self.assertEqual(view._back_btn.text(), "Cancelar")
        self.assertTrue(view._back_btn.isEnabled())
        self.assertEqual(view._next_btn.text(), "Processando...")
        self.assertFalse(view._next_btn.isEnabled())
        self.assertTrue(view._is_processing())

        # Clean up worker thread
        if view.prep_worker:
            _join_worker(view.prep_worker)

    def test_cancel_clicked_stops_processing_and_restores_ui(self) -> None:
        """Verify that canceling an active preparation restores search controls and resets the buttons."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source())
        view._on_next_clicked()
        
        # Click cancel
        view._on_back_or_cancel_clicked()
        
        self.assertTrue(view.search_btn.isEnabled())
        self.assertTrue(view.current_user_btn.isEnabled())
        self.assertEqual(view._back_btn.text(), "Voltar")
        self.assertEqual(view._next_btn.text(), "Recuperar tudo")
        self.assertTrue(view._next_btn.isEnabled())
        self.assertFalse(view._is_processing())

        # Clean up worker thread
        for w in view._old_prep_workers:
            _join_worker(w)


class TestAdminRestoreSearch(unittest.TestCase):
    """Tests for client-side filtering and query matching behavior."""

    def _source(self, name: str, profiles: list | None = None) -> AdminBackupSource:
        return AdminBackupSource(
            path=Path(f"C:/{name}"), name=name, origin="local", machine_id="",
            total_bytes=100, raiz=None,
            profiles=profiles or [UserProfileDetail(name="x", size_bytes=1, modified_time=1.0, path=Path("P"))],
        )

    def test_source_matches_query_by_literal_text(self) -> None:
        """Client-side filtering should match the source name by literal text."""
        src = self._source("OS_5GLPI30327_PMC_125678")
        self.assertTrue(AdminRestoreView._source_matches_query(src, "PMC_125678"))
        self.assertFalse(AdminRestoreView._source_matches_query(src, "unrelated"))

    def test_apply_client_filter_hides_non_matching_cards(self) -> None:
        view = AdminRestoreView()
        match_src = self._source("OS_5_PMC_600259")
        other_src = self._source("OTHER_MACHINE")
        view._on_source_found(match_src)
        view._on_source_found(other_src)
        match_card = next(c for c in view.cards if c.source.path == match_src.path)
        other_card = next(c for c in view.cards if c.source.path == other_src.path)

        view._apply_client_filter("600259")
        self.assertFalse(match_card.isHidden())
        self.assertTrue(other_card.isHidden())

        view._apply_client_filter("")
        self.assertFalse(other_card.isHidden())

    def test_apply_client_filter_skips_deleted_card_without_raising(self) -> None:
        """Regression test: a stale (already-deleted) card reference must not
        crash the client-side filter — see _apply_client_filter's RuntimeError guard."""
        view = AdminRestoreView()
        view._on_source_found(self._source("OS_5_PMC_600259"))
        stale_card = view.cards[0]
        sip.delete(stale_card)  # simulate a widget deleted out from under the list

        view._apply_client_filter("")  # must not raise

        self.assertEqual(view.cards, [])


class TestAdminRestoreLazyStats(unittest.TestCase):
    """Tests for the PENDING_STATS placeholder display and its refresh once
    AdminSourceDetailWorker's lazily-computed sizes arrive."""

    def _pending_source(self) -> AdminBackupSource:
        profile = UserProfileDetail(
            name="29107", size_bytes=0, modified_time=1.0, path=Path("P"), file_count=PENDING_STATS,
        )
        raiz = RaizDetail(size_bytes=0, file_count=PENDING_STATS, dir_count=PENDING_STATS, path=Path("R"))
        return AdminBackupSource(
            path=Path("C:/OS_5"), name="OS_5", origin="local", machine_id="",
            total_bytes=PENDING_STATS, raiz=raiz, profiles=[profile],
        )

    def test_source_card_shows_profile_count_only_while_pending(self) -> None:
        card = SourceCard(self._pending_source())
        self.assertEqual(card._stats_lbl.text(), "1 perfil")

    def test_raiz_card_shows_calculando_while_pending(self) -> None:
        card = RaizDetailCard()
        card.populate(self._pending_source().raiz)
        self.assertEqual(card._val_lbl.text(), "Calculando...")

    def test_profile_row_shows_calculando_while_pending(self) -> None:
        row = ProfileRow(self._pending_source().profiles[0])
        # The size label is the last widget added in ProfileRow._build().
        size_lbl = row.layout().itemAt(row.layout().count() - 1).widget()
        self.assertEqual(size_lbl.text(), "Calculando...")

    def test_source_details_loaded_refreshes_selected_source_and_card(self) -> None:
        view = AdminRestoreView()
        pending = self._pending_source()
        view._on_source_found(pending)
        # Simulate the selection state _on_source_card_clicked() would set up,
        # without going through it directly — that method also kicks off a
        # real AdminSourceDetailWorker thread for PENDING_STATS sources, which
        # would race with the synchronous _on_source_details_loaded() call
        # below in this test.
        view.selected_source = pending
        view._populate_details(pending)

        detailed_profile = UserProfileDetail(
            name="29107", size_bytes=500, modified_time=1.0, path=Path("P"), file_count=1,
        )
        detailed_raiz = RaizDetail(size_bytes=200, file_count=1, dir_count=1, path=Path("R"))
        detailed = AdminBackupSource(
            path=pending.path, name=pending.name, origin=pending.origin, machine_id="",
            total_bytes=700, raiz=detailed_raiz, profiles=[detailed_profile],
        )

        view._on_source_details_loaded(detailed)

        self.assertEqual(view.selected_source.total_bytes, 700)
        card = next(c for c in view.cards if c.source.path == pending.path)
        self.assertIn("700 B", card._stats_lbl.text())


if __name__ == "__main__":
    unittest.main()
