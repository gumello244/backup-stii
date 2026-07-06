from __future__ import annotations

"""Admin authentication dialog for password entry.

Mimics SONICO's authentication flow.
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt
from ui.assets import STYLESHEET


class AdminAuthDialog(QDialog):
    """Password modal for entering admin mode, mimicking SONICO.

    Example:
        dlg = AdminAuthDialog(parent)
        if dlg.exec():
            pwd = dlg.get_password()
    """

    def __init__(self, parent: object = None) -> None:
        super().__init__(parent)  # type: ignore
        self.setWindowTitle("Modo Admin")
        self.setFixedWidth(300)
        self.setStyleSheet(STYLESHEET)
        self._init_ui()

    def _init_ui(self) -> None:
        """Set up layouts and widgets."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        lbl = QLabel("Insira senha de administrador:", self)
        lbl.setObjectName("MutedLabel")
        layout.addWidget(lbl)

        self._setup_input(layout)
        self._setup_button(layout)

    def _setup_input(self, layout: QVBoxLayout) -> None:
        """Create and style the password input."""
        self.pwd_input = QLineEdit(self)
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setStyleSheet("""
            QLineEdit {
                padding: 6px;
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                background-color: #FFFFFF;
                color: #1A202C;
            }
            QLineEdit:focus {
                border: 1px solid #3B6EA5;
            }
        """)
        layout.addWidget(self.pwd_input)

    def _setup_button(self, layout: QVBoxLayout) -> None:
        """Create and configure the submit button."""
        self.btn = QPushButton("Desbloquear", self)
        self.btn.setObjectName("PrimaryButton")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self.accept)
        layout.addWidget(self.btn)

    def get_password(self) -> str:
        """Return the password typed by the user."""
        return self.pwd_input.text()
