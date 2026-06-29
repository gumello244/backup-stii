from __future__ import annotations

"""Tela 2 — Análise & Fonte Resolvida.

Apresenta o progresso de descoberta e mesclagem de backups e, em seguida,
um grid bento assimétrico com o resumo quando as fontes forem resolvidas.

Estados da View:
  - descobrindo: spinner + "Verificando backups..."
  - sem fonte: painel de erro + botão "Buscar novamente"
  - mesclando: spinner + "Comparando versões..."
  - resolvido: BentoGrid com as informações de origem do backup

Example:
    view = AnalysisView()
    view.set_discovering()
    view.set_resolved(merged_file_set)
"""
from datetime import datetime
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from services.backup_merger import MergedFileSet
from ui.components import BentoBox, BentoGrid, BentoSpinner
from ui.assets import RM_RED, RM_TEXT_MUTED
from ui.format_utils import format_bytes as _format_bytes


class AnalysisView(QWidget):
    """Tela 2: source analysis and merge resolution using Bento Grid.

    Example:
        v = AnalysisView()
        v.next_requested.connect(go_to_confirm)
    """

    next_requested = pyqtSignal()
    back_requested = pyqtSignal()
    retry_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._is_error_state: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(14)

        # Centered header
        self._title = QLabel("Análise de Fontes", self)
        self._title.setObjectName("ViewTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._subtitle = QLabel("O Remos está processando seus backups disponíveis.", self)
        self._subtitle.setObjectName("ViewSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        # Dynamic state panel container
        self._state_container = QWidget(self)
        self._state_layout = QVBoxLayout(self._state_container)
        self._state_layout.setContentsMargins(0, 0, 0, 0)
        self._state_layout.setSpacing(0)
        self._state_layout.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._state_container, stretch=1)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)

        self._next_btn = QPushButton("Continuar com esse backup", self)
        self._next_btn.setObjectName("PrimaryButton")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._on_next_clicked)

        # Place buttons side-by-side and centered at the bottom of the window
        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._next_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

    def _on_next_clicked(self) -> None:
        """Route the next button click depending on the current error state."""
        if self._is_error_state:
            self.retry_requested.emit()
            return
        self.next_requested.emit()

    def _clear_layout(self) -> None:
        """Safely delete all children inside the state layout."""
        while self._state_layout.count():
            item = self._state_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _show_spinner_line(self, message: str) -> None:
        """Display a single line spinner + message."""
        self._clear_layout()
        line = QWidget(self)
        lay = QHBoxLayout(line)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.setAlignment(Qt.AlignCenter)

        spinner = BentoSpinner(line)
        label = QLabel(message, line)
        label.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px; background: transparent;")

        lay.addWidget(spinner)
        lay.addWidget(label)
        self._state_layout.addWidget(line)

    def _show_error_panel(self, title: str, desc: str) -> None:
        """Display centered error text block."""
        self._clear_layout()
        panel = QWidget(self)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignCenter)

        title_lbl = QLabel(title, panel)
        title_lbl.setStyleSheet(f"color: {RM_RED}; font-size: 17px; font-weight: 700; background: transparent;")
        title_lbl.setAlignment(Qt.AlignCenter)

        desc_lbl = QLabel(desc, panel)
        desc_lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; font-size: 13px; background: transparent;")
        desc_lbl.setAlignment(Qt.AlignCenter)
        desc_lbl.setWordWrap(True)

        lay.addWidget(title_lbl)
        lay.addWidget(desc_lbl)
        self._state_layout.addWidget(panel)

    def _show_bento_grid(self, merged: MergedFileSet, admin_mode: bool) -> None:
        """Construct the asymmetric 2x2 Bento grid."""
        self._clear_layout()
        grid = BentoGrid(spacing=8, parent=self)

        # 1. Hero Card
        if admin_mode:
            hero = BentoBox(
                title="FONTE",
                value=merged.source_summary,
                subtitle="Origem dos arquivos",
                variant="hero",
                parent=self,
            )
        else:
            hero = self._create_user_hero_box(merged)

        # 2. Size Card
        size_str = _format_bytes(merged.total_bytes)
        size_card = BentoBox(
            title="TAMANHO TOTAL",
            value=size_str,
            subtitle="Volume consolidado",
            variant="default",
            parent=self,
        )

        # 3. Files/Folders Card
        file_count = len(merged.files)
        folder_count = len(merged.by_folder)
        file_suffix = "arquivo" if file_count == 1 else "arquivos"
        folder_suffix = "pasta" if folder_count == 1 else "pastas"
        files_card = BentoBox(
            title="ENCONTRADOS",
            value=f"{file_count} {file_suffix}",
            subtitle=f"Em {folder_count} {folder_suffix}",
            variant="default",
            parent=self,
        )

        # Layout spans: hero spans rows 0 and 1, others occupy column 1
        grid.add_card(hero, 0, 0, rowspan=2, colspan=1)
        grid.add_card(size_card, 0, 1, rowspan=1, colspan=1)
        grid.add_card(files_card, 1, 1, rowspan=1, colspan=1)

        self._state_layout.addWidget(grid)

    def _create_user_hero_box(self, merged: MergedFileSet) -> BentoBox:
        """Create date hero BentoBox for user mode."""
        if not merged.files:
            return BentoBox(
                title="ARQUIVOS SALVOS EM",
                value="--/--/----",
                subtitle="",
                variant="hero",
                parent=self,
            )
        newest_ts = max(f.modified_time for f in merged.files)
        dt = datetime.fromtimestamp(newest_ts)
        day_month_year = dt.strftime("%d/%m/%Y")
        return BentoBox(
            title="ARQUIVOS SALVOS EM",
            value=day_month_year,
            subtitle="",
            variant="hero",
            parent=self,
        )

    # ------------------------------------------------------------------
    # State transitions (Public API)
    # ------------------------------------------------------------------

    def set_discovering(self) -> None:
        """Show "searching for backups" state."""
        self._is_error_state = False
        self._subtitle.setVisible(True)
        self._subtitle.setText("Buscando seus arquivos de backup no servidor e no computador...")
        self._next_btn.setText("Continuar com esse backup")
        self._next_btn.setEnabled(False)
        self._show_spinner_line("Verificando backups disponíveis...")

    def set_merging(self) -> None:
        """Show "comparing file versions" state."""
        self._is_error_state = False
        self._subtitle.setVisible(True)
        self._subtitle.setText("Comparando e selecionando as versões mais recentes dos seus arquivos...")
        self._next_btn.setText("Continuar com esse backup")
        self._next_btn.setEnabled(False)
        self._show_spinner_line("Comparando versões dos arquivos...")

    def set_no_source(self) -> None:
        """Show "no backup found" error state."""
        self._is_error_state = True
        self._subtitle.setVisible(False)
        self._next_btn.setText("Buscar novamente")
        self._next_btn.setEnabled(True)
        self._show_error_panel(
            title="Nenhum backup encontrado",
            desc="Não foi possível acessar a rede ou encontrar pastas locais de backup.\nVerifique a conexão e tente de novo.",
        )

    def set_resolved(self, merged: MergedFileSet, admin_mode: bool = False) -> None:
        """Show summary card with merge results."""
        self._is_error_state = False
        self._subtitle.setVisible(True)
        if admin_mode:
            self._subtitle.setText("Mesclagem concluída para o administrador.")
        else:
            self._subtitle.setText("Pronto! Encontramos um backup elegível para restauração.")
        self._next_btn.setText("Continuar com esse backup")
        self._next_btn.setEnabled(True)
        self._show_bento_grid(merged, admin_mode)
