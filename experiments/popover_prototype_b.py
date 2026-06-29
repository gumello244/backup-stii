from __future__ import annotations

import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame,
    QRadioButton, QButtonGroup,
)

# Established Remos colors
RM_BG = "#FFFFFF"
RM_SURFACE = "#F9F9F9"
RM_BORDER = "#EEEEEE"
RM_TEXT = "#1A202C"
RM_TEXT_MUTED = "#718096"
RM_ACCENT = "#3B6EA5"
RM_RED = "#C0392B"

STYLESHEET = f"""
QMainWindow {{
    background-color: {RM_BG};
}}
QWidget {{
    font-family: 'Segoe UI', -apple-system, sans-serif;
    font-size: 13px;
    color: {RM_TEXT};
}}
QFrame#PopoverCard {{
    background-color: {RM_SURFACE};
    border: 1px solid {RM_BORDER};
    border-radius: 16px;
}}
QLabel#ViewTitle {{
    font-size: 18px;
    font-weight: 700;
    color: {RM_TEXT};
}}
QLabel#ViewSubtitle {{
    font-size: 12px;
    color: {RM_TEXT_MUTED};
}}
QLabel#StepItem {{
    font-size: 12px;
    color: {RM_TEXT_MUTED};
    font-weight: 500;
}}
QLabel#StepItemActive {{
    font-size: 12px;
    color: {RM_ACCENT};
    font-weight: 700;
}}
QLabel#StatusCapsule {{
    background-color: #EBF3FC;
    color: {RM_ACCENT};
    font-size: 12px;
    font-weight: 600;
    padding: 6px 12px;
    border-radius: 14px;
}}
QLabel#DetailsLabel {{
    font-size: 13px;
    font-weight: 500;
    color: {RM_TEXT};
}}
QPushButton#PrimaryButton {{
    background-color: {RM_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 6px 16px;
    font-weight: 600;
}}
QPushButton#SecondaryButton {{
    background-color: #FFFFFF;
    color: {RM_TEXT};
    border: 1px solid {RM_BORDER};
    border-radius: 6px;
    padding: 6px 16px;
}}
"""


class Spinner(QWidget):
    """Simple animated loading spinner styled with Remos signature accent."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)
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
        pen = QPen(QColor(RM_ACCENT), 2.5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(-9, -9, 18, 18, 0, 270 * 16)


class PopoverPrototypeB(QMainWindow):
    """Popover Prototype B: Centered modal card split horizontally inside."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Popover B (Remos Palette)")
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

        body_container = QWidget()
        body_layout = QHBoxLayout(body_container)
        body_layout.setContentsMargins(30, 16, 30, 16)

        self._setup_card(body_layout)
        main_layout.addWidget(body_container)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        """Create state toggling controls for A/B testing."""
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #F0F4F8; border-bottom: 1px solid {RM_BORDER};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Popover B — Estado do Teste:")
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

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(20)

        self._setup_left_panel(card_layout)
        self._setup_divider(card_layout)
        self._setup_right_panel(card_layout)
        self._update_ui_state(3)

    def _setup_left_panel(self, layout: QHBoxLayout) -> None:
        left_pane = QWidget()
        lay = QVBoxLayout(left_pane)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(12)

        lbl = QLabel("PASSO A PASSO")
        lbl.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {RM_TEXT_MUTED};")
        lay.addWidget(lbl)

        steps = [
            ("1. Boas-vindas", False),
            ("2. Análise Técnica", True),
            ("3. Escolha & Confirmar", False),
            ("4. Copiar Dados", False),
            ("5. Conclusão", False),
        ]
        for name, active in steps:
            item = QLabel(name)
            item.setObjectName("StepItemActive" if active else "StepItem")
            lay.addWidget(item)
        lay.addStretch()
        layout.addWidget(left_pane)

    def _setup_divider(self, layout: QHBoxLayout) -> None:
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet(f"background-color: {RM_BORDER}; max-width: 1px; border: none;")
        layout.addWidget(divider)

    def _setup_right_panel(self, layout: QHBoxLayout) -> None:
        right_pane = QWidget()
        lay = QVBoxLayout(right_pane)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        self._title = QLabel("Análise Técnica")
        self._title.setObjectName("ViewTitle")
        lay.addWidget(self._title)

        self._subtitle = QLabel("O Remos está validando seu backup.")
        self._subtitle.setObjectName("ViewSubtitle")
        lay.addWidget(self._subtitle)

        self._state_panel = QFrame()
        self._state_layout = QVBoxLayout(self._state_panel)
        self._state_layout.setContentsMargins(0, 0, 0, 0)
        self._state_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lay.addWidget(self._state_panel, stretch=1)

        self._setup_buttons(lay)
        layout.addWidget(right_pane, stretch=1)

    def _setup_buttons(self, layout: QVBoxLayout) -> None:
        btn_row = QHBoxLayout()
        self._back_btn = QPushButton("Voltar")
        self._back_btn.setObjectName("SecondaryButton")
        btn_row.addWidget(self._back_btn)

        btn_row.addStretch()

        self._next_btn = QPushButton("Avançar")
        self._next_btn.setObjectName("PrimaryButton")
        btn_row.addWidget(self._next_btn)
        layout.addLayout(btn_row)

    def _on_state_changed(self, state_id: int) -> None:
        self._update_ui_state(state_id)

    def _update_ui_state(self, state_id: int) -> None:
        self._clear_layout(self._state_layout)
        if state_id == 0:
            self._show_loading("Escaneando arquivos locais e em rede...")
        elif state_id == 1:
            self._show_loading("Montando estrutura consolidada...")
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
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        spinner = Spinner()
        lbl = QLabel(msg)
        lbl.setStyleSheet(f"color: {RM_TEXT_MUTED};")
        lbl.setWordWrap(True)

        lay.addWidget(spinner)
        lay.addWidget(lbl, stretch=1)
        self._state_layout.addWidget(widget)

    def _show_error(self) -> None:
        self._next_btn.setEnabled(False)
        self._subtitle.setVisible(False)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        err_title = QLabel("Erro na Conexão")
        err_title.setStyleSheet(f"color: {RM_RED}; font-size: 15px; font-weight: 700;")

        err_desc = QLabel("Não detectamos nenhum backup disponível. Conecte-se e tente de novo.")
        err_desc.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 12px;")
        err_desc.setWordWrap(True)

        retry_btn = QPushButton("Tentar Novamente")
        retry_btn.setObjectName("SecondaryButton")
        retry_btn.setFixedWidth(140)

        lay.addWidget(err_title)
        lay.addWidget(err_desc)
        lay.addWidget(retry_btn)
        self._state_layout.addWidget(widget)

    def _show_resolved(self) -> None:
        self._next_btn.setEnabled(True)
        self._subtitle.setVisible(True)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        capsule = QLabel("Backup: 24/06/2026")
        capsule.setObjectName("StatusCapsule")
        capsule.setFixedWidth(160)
        capsule.setAlignment(Qt.AlignCenter)

        desc = QLabel("9 arquivos  •  3 pastas  •  2,3 GB")
        desc.setObjectName("DetailsLabel")

        lay.addWidget(capsule)
        lay.addWidget(desc)
        self._state_layout.addWidget(widget)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PopoverPrototypeB()
    window.show()
    sys.exit(app.exec_())
