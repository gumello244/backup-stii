from __future__ import annotations

"""Unit tests for Bento Grid design system components."""
import sys
import unittest
from PyQt5.QtWidgets import QApplication, QWidget, QLabel

from ui.components import BentoBox, BentoGrid, BentoSpinner
from ui.views.confirm_view import ConfirmView
from services.backup_merger import MergedFileSet, FolderSummary, MergedFile
from pathlib import Path

# Create a headless QApplication for testing widget classes
app = QApplication.instance() or QApplication(sys.argv)


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

        # Verify folder selection card minimum and maximum height constraints
        self.assertEqual(view._folder_card.minimumHeight(), 166)
        self.assertEqual(view._folder_card.maximumHeight(), 166)




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


if __name__ == "__main__":
    unittest.main()
