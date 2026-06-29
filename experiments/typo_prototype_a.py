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
    font-size: 24px;
    font-weight: 800;
    color: {RM_TEXT};
    letter-spacing: -0.5px;
}}
QLabel#ViewSubtitle {{
    font-size: 14px;
    color: {RM_TEXT_MUTED};
    line-height: 1.4;
}}
QLabel#LargeNumber {{
    font-size: 38px;
    font-weight: 800;
    color: {RM_ACCENT};
    letter-spacing: -1px;
}}
QLabel#NumberUnit {{
    font-size: 14px;
    font-weight: 700;
    color: {RM_TEXT};
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
QLabel#NumberLabel {{
    font-size: 12px;
    color: {RM_TEXT_MUTED};
}}
QPushButton#PrimaryButton {{
    background-color: {RM_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 20px;
    font-weight: 600;
}}
QPushButton#SecondaryButton {{
    background-color: #FFFFFF;
    color: {RM_TEXT};
    border: 1px solid {RM_BORDER};
    border-radius: 6px;
    padding: 7px 20px;
}}
"""


class Spinner(QWidget):
    """Simple animated loading spinner styled with Remos signature accent."""

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
        pen = QPen(QColor(RM_ACCENT), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(-11, -11, 22, 22, 0, 270 * 16)


class TypoPrototypeA(QMainWindow):
    """Typo Prototype A: Centered modal card emphasizing strong bold typography."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Typo A (Unified Typography)")
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
        body_layout.setContentsMargins(36, 16, 36, 16)

        self._setup_card(body_layout)
        main_layout.addWidget(body_container)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        """Create state toggling controls for A/B testing."""
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #F0F4F8; border-bottom: 1px solid {RM_BORDER};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Typo A — Estado do Teste:")
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
        card_layout.setContentsMargins(32, 28, 32, 24)
        card_layout.setSpacing(14)

        self._setup_card_header(card_layout)
        self._setup_card_body(card_layout)
        self._setup_card_buttons(card_layout)
        self._update_ui_state(3)

    def _setup_card_header(self, layout: QVBoxLayout) -> None:
        self._title = QLabel("Análise de Fontes")
        self._title.setObjectName("ViewTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle = QLabel("O Remos está reunindo as cópias de segurança locais e de rede.")
        self._subtitle.setObjectName("ViewSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._subtitle)

    def _setup_card_body(self, layout: QVBoxLayout) -> None:
        self._state_panel = QFrame()
        self._state_layout = QVBoxLayout(self._state_panel)
        self._state_layout.setContentsMargins(0, 8, 0, 8)
        self._state_layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._state_panel, stretch=1)

    def _setup_card_buttons(self, layout: QVBoxLayout) -> None:
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
            self._show_loading("Verificando a existência de backups do usuário...")
        elif state_id == 1:
            self._show_loading("Avaliando datas de modificação e comparando versões...")
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
        lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px; font-weight: 500;")
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

        err_title = QLabel("Nenhum backup encontrado")
        err_title.setStyleSheet(f"color: {RM_RED}; font-size: 17px; font-weight: 700; letter-spacing: -0.3px;")
        err_title.setAlignment(Qt.AlignCenter)

        err_desc = QLabel("Não foi possível acessar a rede ou encontrar pastas locais de backup.")
        err_desc.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px;")
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
        lay = QHBoxLayout(widget)
        lay.setSpacing(28)
        lay.setAlignment(Qt.AlignCenter)

        self._add_stat_column(lay, "2,3", "GB", "Total para Restaurar")
        self._add_stat_column(lay, "9", "Arquivos", "3 pastas mapeadas")
        self._add_stat_column(lay, "24", "Junho 2026", "Último backup")

        self._state_layout.addWidget(widget)

    def _add_stat_column(self, parent_layout: QHBoxLayout, num: str, unit: str, label: str) -> None:
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lay.setAlignment(Qt.AlignCenter)

        num_lbl = QLabel(num)
        num_lbl.setObjectName("LargeNumber")
        num_lbl.setAlignment(Qt.AlignCenter)

        unit_lbl = QLabel(unit)
        unit_lbl.setObjectName("NumberUnit")
        unit_lbl.setAlignment(Qt.AlignCenter)

        desc_lbl = QLabel(label)
        desc_lbl.setObjectName("NumberLabel")
        desc_lbl.setAlignment(Qt.AlignCenter)

        lay.addWidget(num_lbl)
        lay.addWidget(unit_lbl)
        lay.addWidget(desc_lbl)
        parent_layout.addWidget(col)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TypoPrototypeA()
    window.show()
    sys.exit(app.exec_())
