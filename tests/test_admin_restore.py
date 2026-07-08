from __future__ import annotations

"""Unit tests for Remos Admin Mode backup restoration logic and UI components."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PyQt5 import sip
from PyQt5.QtWidgets import QApplication

from services.backup_copier import resolve_dest_path
from services.backup_merger import MergedFile
from services.admin_backup_discovery import (
    PENDING_STATS,
    AdminBackupSource,
    RaizDetail,
    UserProfileDetail,
    compile_admin_restore_files,
)
from ui.views.admin_restore_view import AdminRestoreView
from ui.views.admin_restore_cards import SourceCard, RaizDetailCard, ProfileRow
from ui.workers import AdminDiscoverSourcesWorker, AdminPrepareRestoreWorker

app = QApplication.instance() or QApplication(sys.argv)


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
    @patch("services.admin_backup_discovery.Path.rglob")
    @patch("services.admin_backup_discovery.Path.iterdir")
    def test_compile_all_scope(self, mock_iterdir: MagicMock, mock_rglob: MagicMock, mock_is_dir: MagicMock) -> None:
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

        mock_file_raiz = MagicMock(spec=Path)
        mock_file_raiz.is_file.return_value = True
        mock_file_raiz.name = "raiz_db.sqlite"
        mock_file_raiz.stat.return_value.st_size = 400
        mock_file_raiz.stat.return_value.st_mtime = 1719100000.0
        mock_file_raiz.relative_to.return_value = Path("raiz_db.sqlite")

        mock_file_user = MagicMock(spec=Path)
        mock_file_user.is_file.return_value = True
        mock_file_user.name = "notes.txt"
        mock_file_user.stat.return_value.st_size = 600
        mock_file_user.stat.return_value.st_mtime = 1719100000.0
        mock_file_user.relative_to.return_value = Path("notes.txt")

        # Fake rglob yields
        def rglob_side_effect(pattern: str) -> list:
            if "RAIZ" in str(self):
                return [mock_file_raiz]
            return [mock_file_user]

        mock_rglob.side_effect = rglob_side_effect
        mock_iterdir.return_value = [Path("C:/OS_5_PMC_600259/USUARIOS/12345/Desktop")]

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
        self.assertIsNotNone(view.raiz_card)
        self.assertIsNotNone(view._next_btn)

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
        """Clicking source with no sub-selection shows 'Restaurar tudo'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source())
        self.assertTrue(view._next_btn.isEnabled())
        self.assertEqual(view._next_btn.text(), "Restaurar tudo")

    def test_raiz_card_hidden_when_no_raiz(self) -> None:
        """RAIZ card must not appear when source has no RAIZ data."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(raiz=False))
        self.assertTrue(view.raiz_card.isHidden())

    def test_raiz_toggle_updates_label(self) -> None:
        """Toggling RAIZ card should update button to 'Restaurar RAIZ'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(profiles=[]))
        view._on_raiz_toggled()
        self.assertEqual(view._next_btn.text(), "Restaurar RAIZ")

    def test_profile_toggle_updates_label(self) -> None:
        """Toggling one profile should update button with its name."""
        view = AdminRestoreView()
        profile = UserProfileDetail(name="joao", size_bytes=200, modified_time=1.0, path=Path("P"))
        view._on_source_card_clicked(self._make_source(raiz=False, profiles=[profile]))
        view._on_profile_toggled(profile)
        self.assertEqual(view._next_btn.text(), "Restaurar joao")

    def test_multi_profile_toggle_updates_label(self) -> None:
        """Selecting two profiles should collapse to 'usuários' to avoid overflow."""
        view = AdminRestoreView()
        p1 = UserProfileDetail(name="alice", size_bytes=200, modified_time=2.0, path=Path("P"))
        p2 = UserProfileDetail(name="bob", size_bytes=300, modified_time=1.0, path=Path("Q"))
        view._on_source_card_clicked(self._make_source(raiz=False, profiles=[p1, p2]))
        view._on_profile_toggled(p1)
        view._on_profile_toggled(p2)
        self.assertEqual(view._next_btn.text(), "Restaurar usuários")

    def test_raiz_plus_profile_combined_label(self) -> None:
        """RAIZ + one profile should be reflected in button label."""
        view = AdminRestoreView()
        profile = UserProfileDetail(name="carol", size_bytes=400, modified_time=1.0, path=Path("P"))
        view._on_source_card_clicked(self._make_source(profiles=[profile]))
        view._on_raiz_toggled()
        view._on_profile_toggled(profile)
        label = view._next_btn.text()
        self.assertIn("RAIZ", label)
        self.assertIn("carol", label)

    def test_second_raiz_toggle_deselects(self) -> None:
        """Toggling RAIZ twice should deselect it and fall back to 'Restaurar tudo'."""
        view = AdminRestoreView()
        view._on_source_card_clicked(self._make_source(profiles=[]))
        view._on_raiz_toggled()  # select
        view._on_raiz_toggled()  # deselect
        self.assertEqual(view._next_btn.text(), "Restaurar tudo")


class TestAdminRestoreSearch(unittest.TestCase):
    """Tests for client-side filtering and hostname/machine-id search matching."""

    def _source(self, name: str, profiles: list | None = None) -> AdminBackupSource:
        return AdminBackupSource(
            path=Path(f"C:/{name}"), name=name, origin="local", machine_id="",
            total_bytes=100, raiz=None,
            profiles=profiles or [UserProfileDetail(name="x", size_bytes=1, modified_time=1.0, path=Path("P"))],
        )

    def test_source_matches_query_via_hostname_machine_id(self) -> None:
        """A hostname query should match via the extracted machine id, mirroring
        scan_admin_backups' matching, even though it's not a literal substring."""
        src = self._source("OS_5GLPI30327_PMC_125678")
        self.assertTrue(AdminRestoreView._source_matches_query(src, "25sti3t125678"))
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
