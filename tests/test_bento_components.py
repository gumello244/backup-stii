from __future__ import annotations

"""Unit tests for Bento Grid design system components."""
import sys
import unittest
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtWidgets import QApplication, QWidget, QLabel

from ui.components import BentoBox, BentoGrid, BentoSpinner
from ui.views.confirm_view import ConfirmView
from ui.views.admin_restore_cards import _ElidedLabel
from services.backup_merger import MergedFileSet, FolderSummary, MergedFile
from pathlib import Path

# Create a headless QApplication for testing widget classes
app = QApplication.instance() or QApplication(sys.argv)


def tearDownModule() -> None:
    """Flush queued Qt events and pending QThreadPool work before the next
    test module runs in this same process (see test_admin_restore's
    tearDownModule for why this matters — pooled worker threads from other
    modules can otherwise stall a later module sharing the process)."""
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(3):
        app.processEvents()


class TestBentoBox(unittest.TestCase):
    """Tests for the BentoBox card component."""

    def test_initialization(self) -> None:
        """Verify BentoBox starts with correct labels and object names."""
        box = BentoBox(
            title="TEST TITLE",
            value="100",
            subtitle="Test Subtitle",
            variant="default",
        )
        self.assertEqual(box.objectName(), "BentoCard")
        self.assertEqual(box._title_lbl.text(), "TEST TITLE")
        self.assertEqual(box._val_lbl.text(), "100")
        self.assertEqual(box._sub_lbl.text(), "Test Subtitle")
        self.assertEqual(box._val_lbl.objectName(), "BentoValue")

    def test_update_content(self) -> None:
        """Verify update_content changes child label texts."""
        box = BentoBox(title="A", value="B", subtitle="C")
        box.update_content("X", "Y", "Z")
        self.assertEqual(box._title_lbl.text(), "X")
        self.assertEqual(box._val_lbl.text(), "Y")
        self.assertEqual(box._sub_lbl.text(), "Z")

    def test_variants(self) -> None:
        """Verify set_variant updates styling objectName mapping."""
        box = BentoBox(title="A", value="B", subtitle="C")

        box.set_variant("hero")
        self.assertEqual(box.objectName(), "BentoCardHero")
        self.assertEqual(box._val_lbl.objectName(), "BentoValueHero")

        box.set_variant("success")
        self.assertEqual(box.objectName(), "BentoCardSuccess")
        self.assertEqual(box._val_lbl.objectName(), "BentoValueSuccess")

        box.set_variant("danger")
        self.assertEqual(box.objectName(), "BentoCardDanger")
        self.assertEqual(box._val_lbl.objectName(), "BentoValueDanger")

    def test_invalid_variant_raises_value_error(self) -> None:
        """Verify set_variant raises ValueError on unsupported variant."""
        box = BentoBox(title="A", value="B", subtitle="C")
        with self.assertRaises(ValueError):
            box.set_variant("unsupported_variant_name")

    def test_layout_stretches_vc_center(self) -> None:
        """Verify that a VCenter-aligned card has stretches at both top and bottom."""
        box = BentoBox(title="A", value="B", subtitle="C", alignment=Qt.AlignVCenter)
        # 3 widgets (title, value, subtitle) + 2 stretches = 5 items in layout
        self.assertEqual(box.layout().count(), 5)

    def test_layout_stretches_top(self) -> None:
        """Verify that a Top-aligned card has a stretch only at the bottom."""
        box = BentoBox(title="A", value="B", subtitle="C", alignment=Qt.AlignTop)
        # 3 widgets + 1 stretch = 4 items in layout
        self.assertEqual(box.layout().count(), 4)

    def test_layout_stretches_empty_title(self) -> None:
        """Verify that an empty title widget is not added to the layout."""
        box = BentoBox(title="", value="B", subtitle="C", alignment=Qt.AlignTop)
        # 2 widgets (value, subtitle) + 1 stretch = 3 items in layout
        self.assertEqual(box.layout().count(), 3)
        self.assertFalse(box._title_lbl.isVisible())


class TestBentoGrid(unittest.TestCase):
    """Tests for the BentoGrid layout component."""

    def test_add_card_and_clear(self) -> None:
        """Verify adding card to grid and clearing them."""
        grid = BentoGrid()
        w1 = QWidget()
        w2 = QWidget()

        grid.add_card(w1, 0, 0)
        grid.add_card(w2, 0, 1)

        # Check layout count
        self.assertEqual(grid._layout.count(), 2)

        # Clear layout and check
        grid.clear()
        self.assertEqual(grid._layout.count(), 0)


class TestBentoSpinner(unittest.TestCase):
    """Tests for the BentoSpinner component."""

    def test_spinner_timer_lifecycle(self) -> None:
        """Verify timer is active and responds to visibility changes."""
        spinner = BentoSpinner()
        self.assertTrue(spinner._timer.isActive())

        # Directly call event handlers to bypass headless event loop dispatching
        spinner.hideEvent(None)
        self.assertFalse(spinner._timer.isActive())

        spinner.showEvent(None)
        self.assertTrue(spinner._timer.isActive())


class TestConfirmView(unittest.TestCase):
    """Tests for the ConfirmView bento visual component."""

    def test_confirm_view_populate(self) -> None:
        """Verify ConfirmView populates with Custom FolderOptionWidget rows correctly."""
        view = ConfirmView()

        # Build a dummy MergedFileSet
        file1 = MergedFile(
            source_path=Path("C:/test_src/Desktop/a.txt"),
            dest_folder="Desktop",
            relative_name="a.txt",
            size_bytes=1024,
            modified_time=1000.0,
        )
        file2 = MergedFile(
            source_path=Path("C:/test_src/Documents/b.txt"),
            dest_folder="Documents",
            relative_name="b.txt",
            size_bytes=2048,
            modified_time=2000.0,
        )

        merged = MergedFileSet(
            files=[file1, file2],
            total_bytes=3072,
            by_folder={
                "Desktop": FolderSummary(file_count=1, total_bytes=1024),
                "Documents": FolderSummary(file_count=1, total_bytes=2048),
            },
            source_summary="Test Source Summary",
        )

        view.populate(merged)

        # Verify checkboxes maps is populated with the correct keys
        self.assertIn("Desktop", view._checkboxes)
        self.assertIn("Documents", view._checkboxes)

        # Verify the layout has the widgets
        self.assertEqual(view._folder_layout.count(), 2)

        # Verify selected folders list
        selected = view._selected_folders()
        self.assertEqual(len(selected), 2)
        self.assertIn("Desktop", selected)
        self.assertIn("Documents", selected)

        # Test toggling select all / deselect all
        view._deselect_all()
        self.assertEqual(len(view._selected_folders()), 0)

        view._select_all()
        self.assertEqual(len(view._selected_folders()), 2)

        # Verify folder selection card can expand vertically instead of being capped.
        self.assertEqual(view._folder_card.minimumHeight(), 146)
        self.assertGreater(view._folder_card.maximumHeight(), view._folder_card.minimumHeight())


    class TestElidedLabel(unittest.TestCase):
        def test_elided_label_size_hint_is_not_text_width(self) -> None:
            label = _ElidedLabel("A" * 200)
            self.assertEqual(label.sizeHint().width(), 0)

    def test_confirm_view_splits_same_folder_by_profile_in_admin_mode(self) -> None:
        """Verify admin restores keep profile-specific rows separate."""
        view = ConfirmView()

        file1 = MergedFile(
            source_path=Path("C:/test_src/USUARIOS/12345/Desktop/a.txt"),
            dest_folder="Desktop",
            relative_name="a.txt",
            size_bytes=1024,
            modified_time=1000.0,
            target_profile="12345",
        )
        file2 = MergedFile(
            source_path=Path("C:/test_src/USUARIOS/67890/Desktop/b.txt"),
            dest_folder="Desktop",
            relative_name="b.txt",
            size_bytes=2048,
            modified_time=2000.0,
            target_profile="67890",
        )

        merged = MergedFileSet(
            files=[file1, file2],
            total_bytes=3072,
            by_folder={
                "Desktop": FolderSummary(file_count=2, total_bytes=3072),
            },
            source_summary="Admin Source Summary",
        )

        view.populate(merged, True)

        self.assertIn("12345::Desktop", view._checkboxes)
        self.assertIn("67890::Desktop", view._checkboxes)
        self.assertEqual(view._folder_layout.count(), 2)

        selected = view._selected_folders()
        self.assertEqual(len(selected), 2)
        self.assertIn("12345::Desktop", selected)
        self.assertIn("67890::Desktop", selected)

    def test_confirm_view_merged_space_cards_user_mode(self) -> None:
        """Verify space cards are merged and show user mode title and hero variant."""
        view = ConfirmView()
        self.assertFalse(hasattr(view, "_needed_card"))
        self.assertEqual(view._hero_card._variant, "hero")

        file1 = MergedFile(
            source_path=Path("C:/test_src/Desktop/a.txt"),
            dest_folder="Desktop",
            relative_name="a.txt",
            size_bytes=100,
            modified_time=1000.0,
        )
        merged = MergedFileSet(
            files=[file1],
            total_bytes=100,
            by_folder={"Desktop": FolderSummary(file_count=1, total_bytes=100)},
            source_summary="User Summary",
        )
        view.populate(merged)
        self.assertEqual(view._hero_card._title_lbl.text(), "ESPAÇO EM DISCO")

    def test_confirm_view_merged_space_cards_admin_mode(self) -> None:
        """Verify space cards are merged and show admin mode title."""
        view = ConfirmView()
        file1 = MergedFile(
            source_path=Path("C:/test_src/USUARIOS/12345/Desktop/a.txt"),
            dest_folder="Desktop",
            relative_name="a.txt",
            size_bytes=100,
            modified_time=1000.0,
            target_profile="12345",
        )
        merged = MergedFileSet(
            files=[file1],
            total_bytes=100,
            by_folder={"Desktop": FolderSummary(file_count=1, total_bytes=100)},
            source_summary="Admin Summary",
        )
        view.populate(merged, True)
        self.assertEqual(view._hero_card._title_lbl.text(), "ESPAÇO NECESSÁRIO")

    def test_confirm_view_options_card_visibility(self) -> None:
        """Verify options card visibility is determined by admin mode and local source origin."""
        view = ConfirmView()
        self.assertTrue(view._options_card.isHidden())

        file1 = MergedFile(Path("C:/test_src/a.txt"), "Desktop", "a.txt", 100, 1000.0)
        merged = MergedFileSet(files=[file1], total_bytes=100)

        # Normal mode -> Hidden
        view.populate(merged, admin_mode=False, is_local=True)
        self.assertTrue(view._options_card.isHidden())

        # Admin mode + Network source -> Hidden
        view.populate(merged, admin_mode=True, is_local=False)
        self.assertTrue(view._options_card.isHidden())

        # Admin mode + Local source -> Visible
        view.populate(merged, admin_mode=True, is_local=True)
        self.assertFalse(view._options_card.isHidden())




class TestSummaryView(unittest.TestCase):
    """Tests for the SummaryView component."""

    def test_summary_view_populate(self) -> None:
        """Verify SummaryView populates metrics cards and handles duration correctly."""
        from ui.views.summary_view import SummaryView
        from services.backup_copier import CopyResult

        view = SummaryView()
        result = CopyResult(
            success=True,
            files_copied=5,
            bytes_copied=10240,
            skipped_files=[],
            failed_files=[],
            cancelled=False,
            duration_seconds=15,
        )

        view.populate(result)

        self.assertEqual(view._files_card._val_lbl.text(), "5 arquivos")
        self.assertEqual(view._bytes_card._val_lbl.text(), "10,0 KB")
        self.assertEqual(view._time_card._val_lbl.text(), "~15 segundos")

    def test_summary_view_try_other_button_visibility(self) -> None:
        """Verify SummaryView displays the try other button only in admin mode."""
        from ui.views.summary_view import SummaryView
        from services.backup_copier import CopyResult

        view = SummaryView()
        result = CopyResult(
            success=True,
            files_copied=1,
            bytes_copied=10,
            skipped_files=[],
            failed_files=[],
            cancelled=False,
            duration_seconds=1,
        )

        view.populate(result, admin_mode=False)
        self.assertTrue(view._try_other_btn.isHidden())

        view.populate(result, admin_mode=True)
        self.assertFalse(view._try_other_btn.isHidden())

    def test_summary_view_partial_success_when_some_files_fail(self) -> None:
        """Most files restored + a few failed must read as partial success,
        not as a full failure (regression test for the "911 copied, 4 failed
        still shown as RESTAURAÇÃO FALHOU" bug)."""
        from ui.views.summary_view import SummaryView
        from services.backup_copier import CopyResult, SkippedFile
        from pathlib import Path

        view = SummaryView()
        result = CopyResult(
            success=False,
            files_copied=911,
            bytes_copied=10240,
            skipped_files=[],
            failed_files=[
                SkippedFile(Path("a.txt"), Path("C:/Users/x/a.txt"), "Permission denied"),
                SkippedFile(Path("b.txt"), Path("C:/Users/x/b.txt"), "pipe busy"),
            ],
            cancelled=False,
            duration_seconds=15,
        )

        view.populate(result)

        self.assertEqual(view._outcome_title.text(), "SUCESSO PARCIAL")

    def test_summary_view_failure_when_nothing_copied(self) -> None:
        """Zero files restored must still read as a full failure."""
        from ui.views.summary_view import SummaryView
        from services.backup_copier import CopyResult, SkippedFile
        from pathlib import Path

        view = SummaryView()
        result = CopyResult(
            success=False,
            files_copied=0,
            bytes_copied=0,
            skipped_files=[],
            failed_files=[SkippedFile(Path("a.txt"), Path("C:/Users/x/a.txt"), "erro")],
            cancelled=False,
            duration_seconds=1,
        )

        view.populate(result)

        self.assertEqual(view._outcome_title.text(), "RESTAURAÇÃO FALHOU")

    def test_summary_view_full_success_when_no_issues(self) -> None:
        """No skipped or failed files must read as a clean success."""
        from ui.views.summary_view import SummaryView
        from services.backup_copier import CopyResult

        view = SummaryView()
        result = CopyResult(
            success=True, files_copied=10, bytes_copied=1024,
            skipped_files=[], failed_files=[], cancelled=False, duration_seconds=1,
        )

        view.populate(result)

        self.assertEqual(view._outcome_title.text(), "SUCESSO")


class TestAnalysisView(unittest.TestCase):
    """Tests for the AnalysisView layout and dimensions."""

    def test_analysis_view_resolved_layout(self) -> None:
        """Verify resolved grid has stacked cards with expected size constraints."""
        from ui.views.analysis_view import AnalysisView
        from services.backup_merger import MergedFileSet

        view = AnalysisView()
        merged = MergedFileSet(
            files=[],
            total_bytes=0,
            by_folder={},
            source_summary="Test Source Summary",
        )
        view.set_resolved(merged, admin_mode=False)

        grid = view._state_layout.itemAt(0).widget()
        self.assertEqual(grid._layout.count(), 2)

        hero = grid._layout.itemAt(0).widget()
        files = grid._layout.itemAt(1).widget()

        self.assertEqual(hero.minimumWidth(), 320)
        self.assertEqual(hero.maximumWidth(), 320)
        self.assertEqual(hero.minimumHeight(), 100)
        self.assertEqual(hero.maximumHeight(), 100)
        self.assertEqual(files.minimumWidth(), 320)
        self.assertEqual(files.maximumWidth(), 320)
        self.assertEqual(files.minimumHeight(), 100)
        self.assertEqual(files.maximumHeight(), 100)


class TestContactsFilter(unittest.TestCase):
    """Verify Contacts folder filtering rules."""

    def test_filter_contacts_folder(self) -> None:
        """Verify Contacts is ignored if it has only one file, otherwise kept."""
        from services.backup_merger import filter_contacts_folder, MergedFile

        f1 = MergedFile(Path("Contacts/a.txt"), "Contacts", "a.txt", 10, 1.0, "alice")
        f2 = MergedFile(Path("Contacts/b.txt"), "Contacts", "b.txt", 10, 1.0, "bob")
        f3 = MergedFile(Path("Contacts/c.txt"), "Contacts", "c.txt", 10, 1.0, "bob")
        f4 = MergedFile(Path("Desktop/d.txt"), "Desktop", "d.txt", 10, 1.0, "alice")

        filtered = filter_contacts_folder([f1, f2, f3, f4])
        # alice has only 1 contacts file (f1) -> ignored
        # bob has 2 contacts files (f2, f3) -> kept
        # alice's desktop file is not Contacts -> kept
        self.assertEqual(len(filtered), 3)
        self.assertNotIn(f1, filtered)
        self.assertIn(f2, filtered)
        self.assertIn(f3, filtered)
        self.assertIn(f4, filtered)


if __name__ == "__main__":
    unittest.main()

