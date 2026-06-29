from __future__ import annotations

import sys
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame,
    QRadioButton, QButtonGroup, QGridLayout,
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
QFrame#BentoCard {{
    background-color: {RM_SURFACE};
    border: 1px solid {RM_BORDER};
    border-radius: 12px;
}}
QFrame#BentoCardHero {{
    background-color: #EBF3FC;
    border: 1px solid #D5E5F7;
    border-radius: 12px;
}}
QLabel#ViewTitle {{
    font-size: 22px;
    font-weight: 800;
    color: {RM_TEXT};
    letter-spacing: -0.5px;
}}
QLabel#ViewSubtitle {{
    font-size: 13px;
    color: {RM_TEXT_MUTED};
}}
QLabel#BentoTitle {{
    font-size: 9px;
    font-weight: 800;
    color: {RM_TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel#BentoValue {{
    font-size: 20px;
    font-weight: 700;
    color: {RM_TEXT};
}}
QLabel#BentoValueHero {{
    font-size: 32px;
    font-weight: 800;
    color: {RM_ACCENT};
    letter-spacing: -1px;
}}
QLabel#BentoSub {{
    font-size: 11px;
    color: {RM_TEXT_MUTED};
}}
QPushButton#PrimaryButton {{
    background-color: {RM_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 8px;
    padding: 8px 22px;
    font-weight: 600;
}}
QPushButton#SecondaryButton {{
    background-color: #FFFFFF;
    color: {RM_TEXT};
    border: 1px solid {RM_BORDER};
    border-radius: 8px;
    padding: 8px 22px;
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
        """Rotate the spinner angle by 30 degrees."""
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


class BentoUnifiedFreePrototype(QMainWindow):
    """BentoUnifiedFreePrototype: Centered header/subtitles & bento layout free on the window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Bento Unified Free Prototype")
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
        self._setup_free_view(main_layout)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #F0F4F8; border-bottom: 1px solid {RM_BORDER};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Unificado Livre — Estado:")
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        bar_layout.addWidget(title)

        self._setup_radio_buttons(bar_layout)
        parent_layout.addWidget(bar)

    def _setup_radio_buttons(self, bar_layout: QHBoxLayout) -> None:
        self._btn_group = QButtonGroup(self)
        states = [("Buscando", 0), ("Comparando", 1), ("Erro", 2), ("Resolvido", 3)]
        for name, val in states:
            rb = QRadioButton(name)
            rb.setStyleSheet("QRadioButton { font-size: 11px; }")
            if val == 3:
                rb.setChecked(True)
            self._btn_group.addButton(rb, val)
            bar_layout.addWidget(rb)
        self._btn_group.buttonClicked[int].connect(self._on_state_changed)

    def _setup_free_view(self, parent_layout: QVBoxLayout) -> None:
        view_container = QWidget()
        view_layout = QVBoxLayout(view_container)
        view_layout.setContentsMargins(40, 24, 40, 24)
        view_layout.setSpacing(14)

        self._setup_header(view_layout)
        self._setup_body(view_layout)
        self._setup_buttons(view_layout)

        parent_layout.addWidget(view_container)
        self._update_ui_state(3)

    def _setup_header(self, layout: QVBoxLayout) -> None:
        self._title = QLabel("Análise de Fontes")
        self._title.setObjectName("ViewTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle = QLabel("O Remos está processando seus backups disponíveis.")
        self._subtitle.setObjectName("ViewSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._subtitle)

    def _setup_body(self, layout: QVBoxLayout) -> None:
        self._state_panel = QFrame()
        self._state_layout = QVBoxLayout(self._state_panel)
        self._state_layout.setContentsMargins(0, 4, 0, 4)
        self._state_layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._state_panel, stretch=1)

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
        """Trigger update of UI state when a simulator state is selected."""
        self._update_ui_state(state_id)

    def _update_ui_state(self, state_id: int) -> None:
        self._clear_layout(self._state_layout)
        if state_id == 0:
            self._show_loading("Verificando backups disponíveis...")
        elif state_id == 1:
            self._show_loading("Comparando versões dos arquivos...")
        elif state_id == 2:
            self._show_error()
        elif state_id == 3:
            self._show_resolved()

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        """Remove all children widgets recursively from a layout."""
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_loading(self, msg: str) -> None:
        self._next_btn.setEnabled(False)
        self._next_btn.setText("Avançar")
        self._subtitle.setVisible(True)

        widget = QWidget()
        lay = QHBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)

        spinner = Spinner()
        lbl = QLabel(msg)
        lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px;")

        lay.addWidget(spinner)
        lay.addWidget(lbl)
        self._state_layout.addWidget(widget)

    def _show_error(self) -> None:
        self._next_btn.setEnabled(True)
        self._next_btn.setText("Buscar novamente")
        self._subtitle.setVisible(False)

        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        err_title = QLabel("Nenhum backup encontrado")
        err_title.setStyleSheet(f"color: {RM_RED}; font-size: 17px; font-weight: 700;")
        err_title.setAlignment(Qt.AlignCenter)

        err_desc = QLabel("Não foi possível acessar a rede ou encontrar pastas locais de backup.\nVerifique a conexão de rede local e tente de novo.")
        err_desc.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px;")
        err_desc.setAlignment(Qt.AlignCenter)

        lay.addWidget(err_title)
        lay.addWidget(err_desc)
        self._state_layout.addWidget(widget)

    def _show_resolved(self) -> None:
        self._next_btn.setEnabled(True)
        self._next_btn.setText("Avançar")
        self._subtitle.setVisible(True)

        grid = QWidget()
        lay = QGridLayout(grid)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        hero = self._create_bento_box("ÚLTIMO BACKUP", "24/06", "Gerado em 2026", True)
        lay.addWidget(hero, 0, 0, 2, 1)

        size = self._create_bento_box("TAMANHO TOTAL", "2.3 GB", "Volume consolidado", False)
        lay.addWidget(size, 0, 1, 1, 1)

        files = self._create_bento_box("ARQUIVOS", "9 arquivos", "Em 3 pastas mapeadas", False)
        lay.addWidget(files, 1, 1, 1, 1)

        self._state_layout.addWidget(grid)

    def _create_bento_box(self, title: str, val: str, sub: str, hero: bool = False) -> QFrame:
        box = QFrame()
        box.setObjectName("BentoCardHero" if hero else "BentoCard")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        t_lbl = QLabel(title)
        t_lbl.setObjectName("BentoTitle")
        v_lbl = QLabel(val)
        v_lbl.setObjectName("BentoValueHero" if hero else "BentoValue")
        s_lbl = QLabel(sub)
        s_lbl.setObjectName("BentoSub")

        lay.addWidget(t_lbl)
        lay.addWidget(v_lbl)
        lay.addWidget(s_lbl)
        return box


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BentoUnifiedFreePrototype()
    window.show()
    sys.exit(app.exec_())
