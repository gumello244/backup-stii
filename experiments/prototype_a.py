from __future__ import annotations

import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame,
    QRadioButton, QButtonGroup,
)

# Design System constants inspired by macOS HIG & Highclip 2.0
BG_COLOR = "#F2F2F7"
SURFACE_COLOR = "#FFFFFF"
BORDER_COLOR = "#E5E5EA"
TEXT_PRIMARY = "#1C1C1E"
TEXT_SECONDARY = "#6E6E73"
ACCENT_BLUE = "#0066FF"
ACCENT_RED = "#FF3B30"

STYLESHEET = f"""
QMainWindow {{
    background-color: {BG_COLOR};
}}
QWidget {{
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QFrame#Sidebar {{
    background-color: {BG_COLOR};
    border-right: 1px solid {BORDER_COLOR};
}}
QLabel#SidebarTitle {{
    font-size: 11px;
    font-weight: 700;
    color: {TEXT_SECONDARY};
    text-transform: uppercase;
}}
QLabel#SidebarItem {{
    font-size: 13px;
    color: {TEXT_PRIMARY};
    padding: 6px 10px;
    border-radius: 6px;
}}
QLabel#SidebarItemActive {{
    font-size: 13px;
    color: #FFFFFF;
    background-color: {ACCENT_BLUE};
    font-weight: 600;
    padding: 6px 10px;
    border-radius: 6px;
}}
QFrame#ContentPane {{
    background-color: {SURFACE_COLOR};
}}
QFrame#StatusCard {{
    background-color: {BG_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 10px;
}}
QLabel#ViewTitle {{
    font-size: 19px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
}}
QLabel#ViewSubtitle {{
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}
QPushButton#PrimaryButton {{
    background-color: {ACCENT_BLUE};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
}}
QPushButton#SecondaryButton {{
    background-color: {SURFACE_COLOR};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 16px;
}}
"""


class Spinner(QWidget):
    """Simple animated canvas loading spinner."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)

    def _rotate(self) -> None:
        if self.isVisible():
            self._angle = (self._angle + 30) % 360
            self.update()

    def paintEvent(self, event: object) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(self._angle)
        pen = QPen(QColor(ACCENT_BLUE), 2.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(-8, -8, 16, 16, 0, 270 * 16)


class PrototypeA(QMainWindow):
    """Prototype A: macOS Settings style with sidebar and options list."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Protótipo A (macOS Settings)")
        self.setFixedSize(600, 400)
        self.setStyleSheet(STYLESHEET)
        self._init_ui()

    def _init_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._setup_state_selector(main_layout)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(0)
        main_layout.addLayout(body_layout)

        self._setup_sidebar(body_layout)
        self._setup_content(body_layout)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        """Create a state toggle bar at the top of the window for demo purposes."""
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #E5E5EA; border-bottom: 1px solid {BORDER_COLOR};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Protótipo A — Alterar Estado do A/B Test:")
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        bar_layout.addWidget(title)

        self._btn_group = QButtonGroup(self)
        states = [("Analisando", 0), ("Comparando", 1), ("Erro", 2), ("Resolvido", 3)]
        for name, val in states:
            rb = QRadioButton(name)
            rb.setStyleSheet("QRadioButton { font-size: 11px; }")
            if val == 3:
                rb.setChecked(True)
            self._btn_group.addButton(rb, val)
            bar_layout.addWidget(rb)

        self._btn_group.buttonClicked[int].connect(self._on_state_changed)
        parent_layout.addWidget(bar)

    def _setup_sidebar(self, parent_layout: QHBoxLayout) -> None:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(160)
        parent_layout.addWidget(sidebar)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(12, 16, 12, 16)
        lay.setSpacing(12)

        lbl = QLabel("Restauração")
        lbl.setObjectName("SidebarTitle")
        lay.addWidget(lbl)

        steps = [
            ("1. Introdução", False),
            ("2. Análise", True),
            ("3. Confirmação", False),
            ("4. Copiando", False),
            ("5. Resumo", False),
        ]
        for name, active in steps:
            step_lbl = QLabel(name)
            step_lbl.setObjectName("SidebarItemActive" if active else "SidebarItem")
            lay.addWidget(step_lbl)
        lay.addStretch()

    def _setup_content(self, parent_layout: QHBoxLayout) -> None:
        content = QFrame()
        content.setObjectName("ContentPane")
        parent_layout.addWidget(content)

        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(24, 20, 24, 20)
        self._content_layout.setSpacing(12)

        self._title = QLabel("Análise de Origem")
        self._title.setObjectName("ViewTitle")
        self._content_layout.addWidget(self._title)

        self._subtitle = QLabel("O Remos está consolidando os backups disponíveis.")
        self._subtitle.setObjectName("ViewSubtitle")
        self._content_layout.addWidget(self._subtitle)

        # Dynamic state panel container
        self._state_panel = QFrame()
        self._state_layout = QVBoxLayout(self._state_panel)
        self._state_layout.setContentsMargins(0, 8, 0, 8)
        self._content_layout.addWidget(self._state_panel)

        self._content_layout.addStretch()

        # Action Buttons
        self._btn_row = QHBoxLayout()
        self._back_btn = QPushButton("Voltar")
        self._back_btn.setObjectName("SecondaryButton")
        self._btn_row.addWidget(self._back_btn)

        self._btn_row.addStretch()

        self._next_btn = QPushButton("Seguir")
        self._next_btn.setObjectName("PrimaryButton")
        self._btn_row.addWidget(self._next_btn)
        self._content_layout.addLayout(self._btn_row)

        self._update_ui_state(3)

    def _on_state_changed(self, state_id: int) -> None:
        self._update_ui_state(state_id)

    def _update_ui_state(self, state_id: int) -> None:
        self._clear_layout(self._state_layout)
        if state_id == 0:
            self._show_loading("Buscando fontes de backup disponíveis...")
        elif state_id == 1:
            self._show_loading("Comparando versões e integridade dos arquivos...")
        elif state_id == 2:
            self._show_error()
        elif state_id == 3:
            self._show_resolved()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_loading(self, msg: str) -> None:
        self._next_btn.setEnabled(False)
        row = QHBoxLayout()
        row.setSpacing(10)
        spinner = Spinner()
        lbl = QLabel(msg)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        row.addWidget(spinner)
        row.addWidget(lbl)
        row.addStretch()
        self._state_layout.addLayout(row)

    def _show_error(self) -> None:
        self._next_btn.setEnabled(False)
        card = QFrame()
        card.setObjectName("StatusCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)

        err_title = QLabel("Nenhum backup encontrado")
        err_title.setStyleSheet(f"color: {ACCENT_RED}; font-weight: 600;")
        err_desc = QLabel("Verifique a sua conexão de rede e tente novamente.")
        err_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")

        retry_btn = QPushButton("Tentar novamente")
        retry_btn.setObjectName("SecondaryButton")
        retry_btn.setFixedWidth(140)

        lay.addWidget(err_title)
        lay.addWidget(err_desc)
        lay.addWidget(retry_btn)
        self._state_layout.addWidget(card)

    def _show_resolved(self) -> None:
        self._next_btn.setEnabled(True)
        card = QFrame()
        card.setObjectName("StatusCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        lbl_date_title = QLabel("ÚLTIMO BACKUP")
        lbl_date_title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {TEXT_SECONDARY};")
        lbl_date_val = QLabel("24 de junho de 2026")
        lbl_date_val.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {ACCENT_BLUE};")

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {BORDER_COLOR}; max-height: 1px; border: none;")

        lbl_desc = QLabel("9 arquivos em 3 pastas  •  2,3 GB")
        lbl_desc.setStyleSheet(f"color: {TEXT_PRIMARY}; font-weight: 500;")

        lay.addWidget(lbl_date_title)
        lay.addWidget(lbl_date_val)
        lay.addWidget(divider)
        lay.addWidget(lbl_desc)

        self._state_layout.addWidget(card)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PrototypeA()
    window.show()
    sys.exit(app.exec_())
