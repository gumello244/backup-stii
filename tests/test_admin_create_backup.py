from __future__ import annotations

"""Unit tests for Remos Admin Mode backup creation logic and UI components."""

import sys
import unittest
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QLabel

from ui.views.admin_create_backup_view import (
    AdminCreateBackupView,
    AdminCreateBackupConfigView,
    LocalSourceCard,
    LocalFolderOptionWidget,
    _SYSTEM_ROOT_FOLDERS
)
from services.backup_merger import MergedFile

app = QApplication.instance() or QApplication(sys.argv)


class TestAdminCreateBackupComponents(unittest.TestCase):
    """Test AdminCreateBackup view and sub-widgets."""

    def test_system_root_folders_contains_ignored(self) -> None:
        """Verify that system root folders exclude tmp and nvidia."""
        self.assertIn("tmp", _SYSTEM_ROOT_FOLDERS)
        self.assertIn("nvidia", _SYSTEM_ROOT_FOLDERS)

    def test_local_source_card_build(self) -> None:
        """Verify LocalSourceCard constructor and updates."""
        card = LocalSourceCard(
            source_type="profile",
            name="joao",
            path=Path("C:/Users/joao"),
            size_bytes=1024,
            modified_time=1719100000.0
        )
        self.assertEqual(card.name, "joao")
        self.assertEqual(card.source_type, "profile")
        self.assertEqual(card.size_bytes, 1024)
        self.assertEqual(card.modified_time, 1719100000.0)

        # Test selecting/updating style
        self.assertFalse(card.selected)
        card.selected = True
        card.update_style()
        self.assertTrue(card.selected)

    def test_local_source_card_logged_in(self) -> None:
        """Verify LocalSourceCard constructor shows 'Logado' tag for active user."""
        card = LocalSourceCard(
            source_type="profile",
            name="maria",
            path=Path("C:/Users/maria"),
            is_logged_in=True
        )
        self.assertEqual(card.name, "maria")
        self.assertTrue(card.is_logged_in)
        # Find the tag label (usually the second QLabel in the layout or children)
        labels = [c for c in card.findChildren(QLabel)]
        tag_labels = [l.text() for l in labels if l.text() in ("Perfil", "Logado", "Disco")]
        self.assertIn("Logado", tag_labels)

    def test_local_folder_option_widget_toggling(self) -> None:
        """Verify LocalFolderOptionWidget toggles checkbox and styles."""
        widget = LocalFolderOptionWidget(
            display_name="Documentos",
            path=Path("C:/Users/joao/Documents"),
            item_type="profile_folder",
            profile="joao"
        )
        self.assertEqual(widget.display_name, "Documentos")
        self.assertEqual(widget.profile, "joao")
        self.assertTrue(widget.selected)

        # Toggle state
        widget.checkbox.setChecked(False)
        self.assertFalse(widget.selected)

    def test_local_folder_option_widget_stats(self) -> None:
        """Verify LocalFolderOptionWidget stats update correctly."""
        widget = LocalFolderOptionWidget(
            display_name="Downloads",
            path=Path("C:/Users/joao/Downloads"),
            item_type="profile_folder",
            profile="joao"
        )
        widget.set_stats(file_count=42, size_bytes=2048576)
        self.assertEqual(widget.file_count, 42)
        self.assertEqual(widget.size_bytes, 2048576)
        self.assertEqual(widget.count_lbl.text(), "42 arquivos")
        self.assertEqual(widget.size_lbl.text(), "2,0 MB")

    def test_admin_create_backup_view_init(self) -> None:
        """Verify AdminCreateBackupView initial state."""
        view = AdminCreateBackupView()
        self.assertTrue(view._right_widget.isHidden())
        self.assertFalse(view._right_placeholder.isHidden())
        self.assertFalse(view._start_btn.isEnabled())

    def test_admin_create_backup_config_view(self) -> None:
        """Verify AdminCreateBackupConfigView initial state and setup."""
        view = AdminCreateBackupConfigView()
        self.assertFalse(view._start_btn.isEnabled())
        self.assertEqual(view._os_input.text(), "")
        self.assertTrue(view._r_network.isChecked())
        self.assertFalse(view._r_local.isChecked())
        self.assertEqual(view._start_btn.text(), "Criar OS e começar backup")
        view._os_input.setText("12345")
        self.assertEqual(view._start_btn.text(), "Começar Backup")
        view._os_input.setText("")
        self.assertEqual(view._start_btn.text(), "Criar OS e começar backup")


        # Test setup
        files = [
            MergedFile(
                source_path=Path("C:/Users/joao/Desktop/test.txt"),
                dest_folder="Desktop",
                relative_name="test.txt",
                size_bytes=100,
                modified_time=1719100000.0
            )
        ]
        view.setup(files, skip_media_exec=True)
        self.assertTrue(view._start_btn.isEnabled())
        self.assertEqual(view._size_card._sub_lbl.text(), "1 arquivos")

    def test_notas_autodesivas_zero_b_exclusion_behavior(self) -> None:
        """Verify that Notas Autodesivas is hidden if its size is 0 B even with file recognized."""
        view = AdminCreateBackupView()
        
        # Instantiate Notas Autodesivas folder widget
        widget = LocalFolderOptionWidget(
            display_name="Notas Autodesivas",
            path=[Path("C:/Users/joao/AppData/Roaming/Microsoft/Sticky Notes")],
            item_type="profile_folder",
            profile="joao"
        )
        view._folder_widgets.append(widget)
        
        # Simulate scanning result: 1 file, 0 B size
        view._folder_files_cache[widget.path[0]] = [
            MergedFile(
                source_path=widget.path[0] / "sticky.sqlite",
                dest_folder="AppData",
                relative_name="sticky.sqlite",
                size_bytes=0,
                modified_time=1719100000.0
            )
        ]
        
        # Recalculate
        view._trigger_recalculate()
        
        # Verify it was hidden and unchecked
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.selected)
        self.assertFalse(widget.checkbox.isChecked())

    def test_grouped_outlook_option_stats_aggregation(self) -> None:
        """Verify that multiple paths for Outlook are aggregated correctly."""
        view = AdminCreateBackupView()
        
        paths = [
            Path("C:/Users/joao/AppData/Local/Microsoft/Outlook"),
            Path("C:/Users/joao/AppData/Roaming/Microsoft/Outlook")
        ]
        widget = LocalFolderOptionWidget(
            display_name="Outlook",
            path=paths,
            item_type="profile_folder",
            profile="joao"
        )
        view._folder_widgets.append(widget)
        
        # Cache scanned files for both paths
        view._folder_files_cache[paths[0]] = [
            MergedFile(source_path=paths[0] / "local.ost", dest_folder="Outlook", relative_name="local.ost", size_bytes=1000, modified_time=1.0)
        ]
        view._folder_files_cache[paths[1]] = [
            MergedFile(source_path=paths[1] / "roaming.xml", dest_folder="Outlook", relative_name="roaming.xml", size_bytes=500, modified_time=2.0)
        ]
        
        view._trigger_recalculate()
        
        # Assert stats consolidated
        self.assertEqual(widget.file_count, 2)
        self.assertEqual(widget.size_bytes, 1500)
        self.assertEqual(widget.count_lbl.text(), "2 arquivos")
        self.assertEqual(widget.size_lbl.text(), "1,5 KB")


