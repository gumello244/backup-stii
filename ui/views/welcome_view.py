from __future__ import annotations

"""Tela 1 — Welcome / Boas-vindas.

Shows the Remos icon, a welcome message, and an "Iniciar" button.
Background discovery starts immediately on construction so that
backup sources are ready by the time the user clicks "Iniciar".

Example:
    view = WelcomeView(session_state)
    view.start_requested.connect(go_to_analysis)
"""
import os
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from ui.assets import asset_path, RM_TEXT_MUTED

# Layout and sizing constants to avoid magic numbers
LOGO_SIZE = 96
START_BUTTON_WIDTH = 160
ADMIN_BUTTON_WIDTH = 90

LAYOUT_MARGIN_LEFT_RIGHT = 40
LAYOUT_MARGIN_TOP_BOTTOM = 20
LAYOUT_SPACING = 12
START_BUTTON_SPACING = 20


class ClickableLabel(QLabel):
    """QLabel that emits a clicked signal on mouse release.

    Example:
        lbl = ClickableLabel()
        lbl.clicked.connect(self.some_slot)
    """
    clicked = pyqtSignal()

    def mousePressEvent(self, event: object) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class WelcomeView(QWidget):
    """First screen: branding + start button.

    Example:
        w = WelcomeView()
        w.start_requested.connect(handle_start)
    """

    start_requested = pyqtSignal()
    about_requested = pyqtSignal()
    admin_mode_unlocked = pyqtSignal()


    def __init__(self, parent: QWidget = None) -> None:
        """Initialize the Welcome view.

        Example:
            view = WelcomeView()
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Build layout with logo, text, buttons, and footer.

        Example:
            self._init_ui()
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            LAYOUT_MARGIN_LEFT_RIGHT,
            LAYOUT_MARGIN_TOP_BOTTOM,
            LAYOUT_MARGIN_LEFT_RIGHT,
            LAYOUT_MARGIN_TOP_BOTTOM,
        )
        layout.setSpacing(LAYOUT_SPACING)

        layout.addStretch()
        self._create_logo(layout)
        self._create_labels(layout)
        self._create_start_btn(layout)
        layout.addStretch()
        self._create_footer(layout)

    def _create_logo(self, layout: QVBoxLayout) -> None:
        """Create clickable big logo above the title.

        Example:
            self._create_logo(layout)
        """
        self._logo_btn = ClickableLabel(self)
        self._logo_btn.setCursor(Qt.PointingHandCursor)
        self._logo_btn.clicked.connect(self.about_requested.emit)
        self._logo_btn.setStyleSheet("background: transparent;")
        path = asset_path("icon.png")
        if not os.path.exists(path):
            path = asset_path("icon.ico")
        if os.path.exists(path):
            pix = QPixmap(path)
            if not pix.isNull():
                pix = pix.scaled(LOGO_SIZE, LOGO_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._logo_btn.setPixmap(pix)
        self._logo_btn.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._logo_btn, alignment=Qt.AlignCenter)

    def _create_labels(self, layout: QVBoxLayout) -> None:
        """Create and add title and subtitle labels.

        Example:
            self._create_labels(layout)
        """
        title = QLabel("Recuperador de Arquivos", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        sub = QLabel("Este aplicativo permite recuperar arquivos de um backup\nou recuperar arquivos de outro computador.", self)
        sub.setObjectName("ViewSubtitle")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(sub)

    def _create_start_btn(self, layout: QVBoxLayout) -> None:
        """Create and add the Start button.

        Example:
            self._create_start_btn(layout)
        """
        layout.addSpacing(START_BUTTON_SPACING)
        self._start_btn = QPushButton("Iniciar", self)
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.setFixedWidth(START_BUTTON_WIDTH)
        self._start_btn.clicked.connect(self.start_requested.emit)
        layout.addWidget(self._start_btn, alignment=Qt.AlignCenter)

    def _create_footer(self, layout: QVBoxLayout) -> None:
        """Create and add the text footer with Admin Mode toggle.

        Example:
            self._create_footer(layout)
        """
        footer_widget = QWidget(self)
        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        
        # Left spacer to offset the admin button width and keep the STII text centered
        left_spacer = QWidget(self)
        left_spacer.setFixedWidth(ADMIN_BUTTON_WIDTH)
        footer_layout.addWidget(left_spacer)
        
        # Left stretch to keep the STII text centered
        footer_layout.addStretch(1)

        self._footer_lbl = QLabel("STII — Secretaria de Tecnologia da Informação e Inovação", self)
        self._footer_lbl.setObjectName("MutedLabel")
        self._footer_lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; background: transparent;")
        footer_layout.addWidget(self._footer_lbl)

        # Right stretch to push the admin button to the far right
        footer_layout.addStretch(1)

        self._admin_btn = QPushButton("Modo admin", self)
        self._admin_btn.setFixedWidth(ADMIN_BUTTON_WIDTH)
        self._admin_btn.setCursor(Qt.PointingHandCursor)
        self._admin_btn.setStyleSheet(f"""
            QPushButton {{
                color: {RM_TEXT_MUTED};
                background: transparent;
                border: none;
                font-size: 11px;
                text-decoration: none;
            }}
            QPushButton:hover {{
                color: #5599ff;
            }}
        """)
        self._admin_btn.clicked.connect(self._on_admin_clicked)
        footer_layout.addWidget(self._admin_btn)

        layout.addWidget(footer_widget)

    def _on_admin_clicked(self) -> None:
        """Prompt user for admin password and navigate to admin view on success."""
        from ui.dialogs import AdminAuthDialog
        from config import get_admin_password
        from PyQt5.QtWidgets import QMessageBox

        dlg = AdminAuthDialog(self)
        if dlg.exec():
            if dlg.get_password() == get_admin_password():
                self.admin_mode_unlocked.emit()
            else:
                QMessageBox.critical(self, "Erro", "Senha inválida.", QMessageBox.Ok)

