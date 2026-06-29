from __future__ import annotations

import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QFrame,
    QRadioButton, QButtonGroup, QGridLayout, QScrollArea,
    QCheckBox,
)

# Established Remos colors
RM_BG = "#FFFFFF"
RM_SURFACE = "#F9F9F9"
RM_BORDER = "#EEEEEE"
RM_TEXT = "#1A202C"
RM_TEXT_MUTED = "#718096"
RM_ACCENT = "#3B6EA5"
RM_RED = "#C0392B"
RM_GREEN = "#27AE60"

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
QFrame#BentoCardHeroSuccess {{
    background-color: #EAF7ED;
    border: 1px solid #D1F2D9;
    border-radius: 12px;
}}
QFrame#BentoCardHeroDanger {{
    background-color: #FDF2F2;
    border: 1px solid #FBD5D5;
    border-radius: 12px;
}}
QLabel#ViewTitle {{
    font-size: 20px;
    font-weight: 800;
    color: {RM_TEXT};
    letter-spacing: -0.5px;
}}
QLabel#BentoTitle {{
    font-size: 8px;
    font-weight: 800;
    color: {RM_TEXT_MUTED};
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QLabel#BentoValue {{
    font-size: 18px;
    font-weight: 700;
    color: {RM_TEXT};
}}
QLabel#BentoValueHeroSuccess {{
    font-size: 22px;
    font-weight: 800;
    color: {RM_GREEN};
}}
QLabel#BentoValueHeroDanger {{
    font-size: 22px;
    font-weight: 800;
    color: {RM_RED};
}}
QLabel#BentoSub {{
    font-size: 10px;
    color: {RM_TEXT_MUTED};
}}
QScrollArea {{
    border: 1px solid {RM_BORDER};
    border-radius: 10px;
    background-color: {RM_SURFACE};
}}
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
    background: transparent;
    padding: 4px;
}}
QPushButton#PrimaryButton {{
    background-color: {RM_ACCENT};
    color: #FFFFFF;
    border: none;
    border-radius: 6px;
    padding: 7px 18px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:disabled {{
    background-color: {RM_BORDER};
    color: {RM_TEXT_MUTED};
}}
QPushButton#SecondaryButton {{
    background-color: #FFFFFF;
    color: {RM_TEXT};
    border: 1px solid {RM_BORDER};
    border-radius: 6px;
    padding: 7px 18px;
}}
QPushButton#LinkButton {{
    background: transparent;
    color: {RM_ACCENT};
    border: none;
    font-size: 12px;
    text-decoration: underline;
}}
"""


class BentoBox(QFrame):
    """Reusable card element following Remos' Bento-grid design system."""

    def __init__(
        self, title: str, value: str, subtitle: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BentoCard")
        self._init_ui(title, value, subtitle)

    def _init_ui(self, title: str, value: str, subtitle: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        self._t_lbl = QLabel(title)
        self._t_lbl.setObjectName("BentoTitle")
        self._v_lbl = QLabel(value)
        self._v_lbl.setObjectName("BentoValue")
        self._s_lbl = QLabel(subtitle)
        self._s_lbl.setObjectName("BentoSub")

        lay.addWidget(self._t_lbl)
        lay.addWidget(self._v_lbl)
        lay.addWidget(self._s_lbl)

    def update_content(self, title: str, value: str, subtitle: str) -> None:
        self._t_lbl.setText(title)
        self._v_lbl.setText(value)
        self._s_lbl.setText(subtitle)

    def set_success_style(self) -> None:
        self.setObjectName("BentoCardHeroSuccess")
        self._v_lbl.setObjectName("BentoValueHero_Success")
        self.setStyleSheet(f"color: {RM_GREEN};")
        self._v_lbl.setStyleSheet(f"color: {RM_GREEN}; font-size: 22px; font-weight: 800;")

    def set_danger_style(self) -> None:
        self.setObjectName("BentoCardHeroDanger")
        self._v_lbl.setObjectName("BentoValueHero_Danger")
        self.setStyleSheet(f"color: {RM_RED};")
        self._v_lbl.setStyleSheet(f"color: {RM_RED}; font-size: 22px; font-weight: 800;")


class BentoGrid(QWidget):
    """Grid container that simplifies adding bento card layouts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

    def add_card(self, card: QWidget, row: int, col: int, rowspan: int = 1, colspan: int = 1) -> None:
        self._layout.addWidget(card, row, col, rowspan, colspan)


class BentoConfirmPrototype(QMainWindow):
    """BentoConfirmPrototype: Redesigned ConfirmView layout utilizing the bento system."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Remos — Confirm Bento Design")
        self.setFixedSize(600, 420)
        self.setStyleSheet(STYLESHEET)
        self._checkboxes: list[QCheckBox] = []
        self._init_ui()

    def _init_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._setup_state_selector(main_layout)
        self._setup_main_layout(main_layout)

    def _setup_state_selector(self, parent_layout: QVBoxLayout) -> None:
        """Create selector controls to switch test scenarios."""
        bar = QFrame()
        bar.setStyleSheet(f"background-color: #F0F4F8; border-bottom: 1px solid {RM_BORDER};")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)

        title = QLabel("Confirmar — Simular cenário:")
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        bar_layout.addWidget(title)

        self._btn_group = QButtonGroup(self)
        states = [("Espaço Suficiente", 0), ("Espaço Insuficiente", 1)]
        for name, val in states:
            rb = QRadioButton(name)
            rb.setStyleSheet("QRadioButton { font-size: 11px; }")
            if val == 0:
                rb.setChecked(True)
            self._btn_group.addButton(rb, val)
            bar_layout.addWidget(rb)

        self._btn_group.buttonClicked[int].connect(self._on_state_changed)
        parent_layout.addWidget(bar)

    def _setup_main_layout(self, parent_layout: QVBoxLayout) -> None:
        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(36, 12, 36, 16)
        lay.setSpacing(8)

        title = QLabel("Confirmar Restauração")
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        self._setup_bento_grid(lay)
        self._setup_folder_list(lay)
        self._setup_bottom_buttons(lay)

        parent_layout.addWidget(body)
        self._on_state_changed(0)

    def _setup_bento_grid(self, layout: QVBoxLayout) -> None:
        self._grid = BentoGrid()
        
        # 1. Hero Status Card (Spans 2 rows)
        self._hero_status = BentoBox("VERIFICAÇÃO DE ESPAÇO", "Espaço Suficiente", "Disco rígido validado")
        self._grid.add_card(self._hero_status, 0, 0, 2, 1)

        # 2. Disk Storage space specs
        self._disk_info = BentoBox("ESPAÇO DO BACKUP", "2,3 GB necessários", "120 GB livres em C:\\")
        self._grid.add_card(self._disk_info, 0, 1, 1, 1)

        # 3. Estimated duration
        self._time_info = BentoBox("TEMPO DE RESTAURAÇÃO", "~4 minutos", "Medido via benchmark")
        self._grid.add_card(self._time_info, 1, 1, 1, 1)

        layout.addWidget(self._grid)

    def _setup_folder_list(self, layout: QVBoxLayout) -> None:
        # Toggle links
        links = QHBoxLayout()
        sel_all = QPushButton("Selecionar tudo")
        sel_all.setObjectName("LinkButton")
        sel_all.clicked.connect(self._select_all)
        desel_all = QPushButton("Deselecionar tudo")
        desel_all.setObjectName("LinkButton")
        desel_all.clicked.connect(self._deselect_all)
        links.addWidget(sel_all)
        links.addWidget(desel_all)
        links.addStretch()
        layout.addLayout(links)

        # Scroll list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        scroll_lay.setContentsMargins(6, 6, 6, 6)
        scroll_lay.setSpacing(4)

        folders = [
            ("Área de Trabalho", "4 arquivos, 1,8 GB"),
            ("Documentos", "3 arquivos, 420 MB"),
            ("Imagens", "2 arquivos, 80 MB"),
        ]
        for name, detail in folders:
            cb = QCheckBox(f"{name}  —  {detail}")
            cb.setChecked(True)
            scroll_lay.addWidget(cb)
            self._checkboxes.append(cb)

        scroll_lay.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, stretch=1)

    def _setup_bottom_buttons(self, layout: QVBoxLayout) -> None:
        btn_row = QHBoxLayout()
        back = QPushButton("Voltar")
        back.setObjectName("SecondaryButton")
        btn_row.addWidget(back)

        btn_row.addStretch()

        self._restore_btn = QPushButton("Restaurar")
        self._restore_btn.setObjectName("PrimaryButton")
        btn_row.addWidget(self._restore_btn)
        layout.addLayout(btn_row)

    def _on_state_changed(self, state_id: int) -> None:
        if state_id == 0:
            self._hero_status.update_content("VERIFICAÇÃO DE ESPAÇO", "Espaço Suficiente", "Disco rígido pronto")
            self._hero_status.set_success_style()
            self._restore_btn.setEnabled(True)
        else:
            self._hero_status.update_content("VERIFICAÇÃO DE ESPAÇO", "Espaço Insuficiente", "Limpe o disco rígido")
            self._hero_status.set_danger_style()
            self._restore_btn.setEnabled(False)

    def _select_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(True)

    def _deselect_all(self) -> None:
        for cb in self._checkboxes:
            cb.setChecked(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BentoConfirmPrototype()
    window.show()
    sys.exit(app.exec_())
