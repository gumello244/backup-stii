from __future__ import annotations

"""Unit tests for the Remos Admin Mode view and welcome-screen entry request."""
import sys
import unittest
from unittest.mock import patch, MagicMock
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QThreadPool

from ui.views.admin_view import AdminView

app = QApplication.instance() or QApplication(sys.argv)


def tearDownModule() -> None:
    """Flush queued Qt events and pending QThreadPool work before the next
    test module runs in this same process (see test_admin_restore's
    tearDownModule for why this matters — pooled worker threads from other
    modules can otherwise stall a later module sharing the process)."""
    QThreadPool.globalInstance().waitForDone(5000)
    for _ in range(3):
        app.processEvents()


class TestAdminFlow(unittest.TestCase):
    """Tests for the Admin Mode authentication and dashboard."""

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

    def test_admin_mode_requested_signal(self) -> None:
        """Verify clicking 'Modo admin' emits admin_mode_requested directly —
        entry is now gated by a Windows UAC prompt (MainWindow._request_admin_mode),
        not an in-app password dialog."""
        from ui.views.welcome_view import WelcomeView
        view = WelcomeView()
        emitted = False

        def on_requested() -> None:
            nonlocal emitted
            emitted = True

        view.admin_mode_requested.connect(on_requested)
        view._admin_btn.click()
        self.assertTrue(emitted)


if __name__ == "__main__":
    unittest.main()
