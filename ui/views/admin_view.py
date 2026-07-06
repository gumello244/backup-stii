from __future__ import annotations

"""AdminView — Screen showing admin options.

Allows admins to select tools like backup restoration, logs, diagnostic tests.
"""

from typing import Optional, Callable
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from ui.components import BentoBox, BentoGrid

# Layout and styling constants to avoid magic numbers
CARD_WIDTH = 185
CARD_MIN_HEIGHT = 95
GRID_SPACING = 12

LAYOUT_MARGIN_LEFT_RIGHT = 40
LAYOUT_MARGIN_TOP_BOTTOM = 30
LAYOUT_SPACING = 16

BACK_BUTTON_WIDTH = 120


class ClickableBentoBox(BentoBox):
    """A BentoBox that acts as a button, triggering a clicked signal.

    Example:
        box = ClickableBentoBox("TITLE", "VALUE", "SUBTITLE")
        box.clicked.connect(self.handle_click)
    """

    clicked = pyqtSignal()

    def mousePressEvent(self, event: object) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class AdminView(QWidget):
    """Admin dashboard presenting tools via bento card boxes.

    Example:
        view = AdminView()
        view.back_requested.connect(go_back)
        view.restore_requested.connect(go_to_restore)
    """

    back_requested = pyqtSignal()
    restore_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Initialize user interface layout and components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            LAYOUT_MARGIN_LEFT_RIGHT,
            LAYOUT_MARGIN_TOP_BOTTOM,
            LAYOUT_MARGIN_LEFT_RIGHT,
            LAYOUT_MARGIN_TOP_BOTTOM,
        )
        layout.setSpacing(LAYOUT_SPACING)

        self._create_header(layout)
        layout.addStretch()
        self._create_grid(layout)
        layout.addStretch()
        self._create_back_button(layout)

    def _create_header(self, layout: QVBoxLayout) -> None:
        """Create header labels and add to layout."""
        title = QLabel("Painel do Administrador", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Selecione a ferramenta administrativa desejada", self)
        subtitle.setObjectName("ViewSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

    def _add_option_card(
        self,
        value: str,
        subtitle: str,
        row: int,
        col: int,
        on_clicked: Optional[Callable] = None,
    ) -> ClickableBentoBox:
        """Create, configure, and add an option bento box to the grid."""
        card = ClickableBentoBox(
            value=value,
            subtitle=subtitle,
            variant="default",
            alignment=Qt.AlignLeft | Qt.AlignTop,
            parent=self,
        )
        card.setFixedWidth(CARD_WIDTH)
        card.setMinimumHeight(CARD_MIN_HEIGHT)
        card.setCursor(Qt.PointingHandCursor)
        if on_clicked:
            card.clicked.connect(on_clicked)
        self._grid.add_card(card, row, col)
        return card

    def _create_grid(self, layout: QVBoxLayout) -> None:
        """Build the bento card grid container."""
        self._grid = BentoGrid(spacing=GRID_SPACING, parent=self)

        self._restore_card = self._add_option_card(
            "Restaurar backups",
            "Recuperar arquivos de backup do usuário",
            0,
            0,
            self._on_restore_clicked,
        )
        self._create_backup_card = self._add_option_card(
            "Criar backup",
            "Criar um novo backup de usuário ou máquina no padrão da TI",
            0,
            1,
        )
        self._transfer_files_card = self._add_option_card(
            "Transferir arquivos",
            "Conectar a outro computador e transferir perfis e arquivos",
            0,
            2,
        )
        self._clean_users_card = self._add_option_card(
            "Limpar perfis",
            "Remover pastas e perfis de usuários específicos do Windows",
            1,
            0,
        )
        self._clean_pc_card = self._add_option_card(
            "Limpar micro",
            "Limpar cache, lixo e corrigir registros com CCleaner CLI",
            1,
            1,
        )

        layout.addWidget(self._grid)

    def _create_back_button(self, layout: QVBoxLayout) -> None:
        """Create and add back button at the bottom."""
        btn_container = QWidget(self)
        btn_layout = QHBoxLayout(btn_container)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.addStretch()

        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setFixedWidth(BACK_BUTTON_WIDTH)
        self._back_btn.clicked.connect(self.back_requested.emit)
        btn_layout.addWidget(self._back_btn)

        layout.addWidget(btn_container)

    def _on_restore_clicked(self) -> None:
        """Handle click event for backup restore option."""
        self.restore_requested.emit()
