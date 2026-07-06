from __future__ import annotations

"""Unit tests for the Remos Admin Mode dialog, view, and password validation flow."""
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from ui.dialogs import AdminAuthDialog
from ui.views.admin_view import AdminView

app = QApplication.instance() or QApplication(sys.argv)


class TestAdminFlow(unittest.TestCase):
    """Tests for the Admin Mode authentication and dashboard."""

    def test_auth_dialog_password(self) -> None:
        """Verify AdminAuthDialog inputs and retrieves password correctly."""
        dlg = AdminAuthDialog()
        dlg.pwd_input.setText("test_pass")
        self.assertEqual(dlg.get_password(), "test_pass")

    def test_admin_view_cards(self) -> None:
        """Verify AdminView contains the expected Bento option cards."""
        view = AdminView()
        self.assertEqual(view._restore_card._val_lbl.text(), "Restaurar backups")
        self.assertEqual(view._create_backup_card._val_lbl.text(), "Criar backup")
        self.assertEqual(view._transfer_files_card._val_lbl.text(), "Transferir arquivos")
        self.assertEqual(view._clean_users_card._val_lbl.text(), "Limpar perfis")
        self.assertEqual(view._clean_pc_card._val_lbl.text(), "Limpar micro")

        # Verify card titles are empty and hidden
        self.assertEqual(view._restore_card._title_lbl.text(), "")
        self.assertFalse(view._restore_card._title_lbl.isVisible())
        self.assertEqual(view._create_backup_card._title_lbl.text(), "")
        self.assertFalse(view._create_backup_card._title_lbl.isVisible())

    def test_admin_view_restore_signal(self) -> None:
        """Verify clicking restore emits the restore_requested signal."""
        view = AdminView()
        signal_emitted = False

        def on_restore() -> None:
            nonlocal signal_emitted
            signal_emitted = True

        view.restore_requested.connect(on_restore)
        view._restore_card.clicked.emit()
        self.assertTrue(signal_emitted)

    def test_admin_view_back_signal(self) -> None:
        """Verify clicking back emits the back_requested signal."""
        view = AdminView()
        signal_emitted = False

        def on_back() -> None:
            nonlocal signal_emitted
            signal_emitted = True

        view.back_requested.connect(on_back)
        view._back_btn.click()
        self.assertTrue(signal_emitted)


class TestWelcomeView(unittest.TestCase):
    """Tests for the WelcomeView component."""

    def test_welcome_view_components(self) -> None:
        """Verify WelcomeView initializes widgets with correct text and alignments."""
        from ui.views.welcome_view import WelcomeView
        view = WelcomeView()
        self.assertEqual(view._start_btn.text(), "Iniciar")
        self.assertEqual(view._admin_btn.text(), "Modo admin")
        self.assertEqual(view._footer_lbl.text(), "STII — Secretaria de Tecnologia da Informação e Inovação")

    def test_start_requested_signal(self) -> None:
        """Verify clicking Iniciar button emits start_requested signal."""
        from ui.views.welcome_view import WelcomeView
        view = WelcomeView()
        emitted = False

        def on_start() -> None:
            nonlocal emitted
            emitted = True

        view.start_requested.connect(on_start)
        view._start_btn.click()
        self.assertTrue(emitted)

    def test_about_requested_signal(self) -> None:
        """Verify clicking logo label emits about_requested signal."""
        from ui.views.welcome_view import WelcomeView
        view = WelcomeView()
        emitted = False

        def on_about() -> None:
            nonlocal emitted
            emitted = True

        view.about_requested.connect(on_about)
        view._logo_btn.clicked.emit()
        self.assertTrue(emitted)

    @patch("ui.dialogs.AdminAuthDialog.exec")
    @patch("ui.dialogs.AdminAuthDialog.get_password")
    @patch("config.get_admin_password")
    def test_admin_mode_unlocked_success(
        self, mock_get_admin_password: MagicMock, mock_get_password: MagicMock, mock_exec: MagicMock
    ) -> None:
        """Verify admin_mode_unlocked is emitted on successful dialog auth."""
        from ui.views.welcome_view import WelcomeView
        mock_exec.return_value = True
        mock_get_password.return_value = "secret"
        mock_get_admin_password.return_value = "secret"

        view = WelcomeView()
        emitted = False

        def on_unlocked() -> None:
            nonlocal emitted
            emitted = True

        view.admin_mode_unlocked.connect(on_unlocked)
        view._admin_btn.click()
        self.assertTrue(emitted)

    @patch("ui.dialogs.AdminAuthDialog.exec")
    @patch("ui.dialogs.AdminAuthDialog.get_password")
    @patch("config.get_admin_password")
    @patch("PyQt5.QtWidgets.QMessageBox.critical")
    def test_admin_mode_unlocked_failed(
        self, mock_critical: MagicMock, mock_get_admin_password: MagicMock, mock_get_password: MagicMock, mock_exec: MagicMock
    ) -> None:
        """Verify admin_mode_unlocked is NOT emitted and critical message dialog is shown on auth failure."""
        from ui.views.welcome_view import WelcomeView
        mock_exec.return_value = True
        mock_get_password.return_value = "wrong_pwd"
        mock_get_admin_password.return_value = "secret"

        view = WelcomeView()
        emitted = False

        def on_unlocked() -> None:
            nonlocal emitted
            emitted = True

        view.admin_mode_unlocked.connect(on_unlocked)
        view._admin_btn.click()
        self.assertFalse(emitted)
        mock_critical.assert_called_once()


if __name__ == "__main__":
    unittest.main()
