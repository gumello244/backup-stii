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
QFrame#PopoverCard {{
    background-color: {SURFACE_COLOR};
    border: 1px solid {BORDER_COLOR};
    border-radius: 16px;
}}
QLabel#ViewTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}
QLabel#ViewSubtitle {{
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}
QLabel#StatusCapsule {{
    background-color: #E5F1FF;
    color: {ACCENT_BLUE};
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: 14px;
}}
QLabel#DetailsLabel {{
    font-size: 14px;
    font-weight: 500;
    color: {TEXT_PRIMARY};
}}
QPushButton#PrimaryButton {{
    background-color: {ACCENT_BLUE};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 18px;
    font-weight: 600;
}}
QPushButton#SecondaryButton {{
    background-color: {SURFACE_COLOR};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 6px;
    padding: 6px 18px;
}}
"""


class Spinner(QWidget):
    """Simple animated canvas loading spinner."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)
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
        pen = QPen(QColor(ACCENT_BLUE), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(-11, -11, 22, 22, 0, 270 * 16)


class PrototypeB(QMainWindow):
    """Prototype B: macOS Setup Assistant style with a centered elevated card."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Protótipo B (macOS Setup Assistant)")
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

        # Centered frame container
        body_container = QWidget()
        body_layout = QHBoxLayout(body_container)
        body_layout.setContentsMargins(36, 16, 36, 16)

        self._setup_card(body_layout)
        main_layout.addWidget(body_container)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        """Create a state toggle bar at the top of the window for demo purposes."""
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #E5E5EA; border-bottom: 1px solid {BORDER_COLOR};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Protótipo B — Alterar Estado do A/B Test:")
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

    def _setup_card(self, parent_layout: QHBoxLayout) -> None:
        card = QFrame()
        card.setObjectName("PopoverCard")
        parent_layout.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(16)

        self._setup_card_header(card_layout)
        self._setup_card_body(card_layout)
        self._setup_card_buttons(card_layout)
        self._update_ui_state(3)

    def _setup_card_header(self, layout: QVBoxLayout) -> None:
        """Create and add header title and subtitle labels to card layout."""
        self._title = QLabel("Análise de Fontes de Backup")
        self._title.setObjectName("ViewTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle = QLabel("O Remos está analisando os arquivos disponíveis para restauração.")
        self._subtitle.setObjectName("ViewSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._subtitle)

    def _setup_card_body(self, layout: QVBoxLayout) -> None:
        """Create and add dynamic state panel to card layout."""
        self._state_panel = QFrame()
        self._state_layout = QVBoxLayout(self._state_panel)
        self._state_layout.setContentsMargins(0, 0, 0, 0)
        self._state_layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._state_panel, stretch=1)

    def _setup_card_buttons(self, layout: QVBoxLayout) -> None:
        """Create and add navigation action buttons row to card layout."""
        btn_row = QHBoxLayout()
        self._back_btn = QPushButton("Voltar")
        self._back_btn.setObjectName("SecondaryButton")
        btn_row.addWidget(self._back_btn)

        btn_row.addStretch()

        self._next_btn = QPushButton("Continuar")
        self._next_btn.setObjectName("PrimaryButton")
        btn_row.addWidget(self._next_btn)
        layout.addLayout(btn_row)

    def _on_state_changed(self, state_id: int) -> None:
        self._update_ui_state(state_id)

    def _update_ui_state(self, state_id: int) -> None:
        self._clear_layout(self._state_layout)
        if state_id == 0:
            self._show_loading("Verificando backups disponíveis...")
        elif state_id == 1:
            self._show_loading("Consolidando versões e arquivos...")
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
        self._subtitle.setVisible(True)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)

        spinner = Spinner()
        lbl = QLabel(msg)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY};")
        lbl.setAlignment(Qt.AlignCenter)

        lay.addWidget(spinner, alignment=Qt.AlignCenter)
        lay.addWidget(lbl)
        self._state_layout.addWidget(widget)

    def _show_error(self) -> None:
        self._next_btn.setEnabled(False)
        self._subtitle.setVisible(False)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)

        err_title = QLabel("Nenhum Backup Encontrado")
        err_title.setStyleSheet(f"color: {ACCENT_RED}; font-size: 16px; font-weight: 700;")
        err_title.setAlignment(Qt.AlignCenter)

        err_desc = QLabel("Não localizamos fontes de backup. Por favor, cheque o cabo de rede.")
        err_desc.setStyleSheet(f"color: {TEXT_SECONDARY};")
        err_desc.setAlignment(Qt.AlignCenter)

        retry_btn = QPushButton("Tentar Novamente")
        retry_btn.setObjectName("SecondaryButton")
        retry_btn.setFixedWidth(150)

        lay.addWidget(err_title)
        lay.addWidget(err_desc)
        lay.addWidget(retry_btn, alignment=Qt.AlignCenter)
        self._state_layout.addWidget(widget)

    def _show_resolved(self) -> None:
        self._next_btn.setEnabled(True)
        self._subtitle.setVisible(True)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)

        capsule = QLabel("Backup Recente: 24/06/2026")
        capsule.setObjectName("StatusCapsule")

        desc = QLabel("9 arquivos em 3 pastas  •  2.3 GB disponíveis")
        desc.setObjectName("DetailsLabel")
        desc.setAlignment(Qt.AlignCenter)

        lay.addWidget(capsule, alignment=Qt.AlignCenter)
        lay.addWidget(desc)
        self._state_layout.addWidget(widget)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PrototypeB()
    window.show()
    sys.exit(app.exec_())
