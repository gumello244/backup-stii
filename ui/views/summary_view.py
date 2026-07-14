from __future__ import annotations

"""Tela 5 — Conclusão / Resumo.

Apresenta o resultado da restauração (sucesso, parcial, cancelado, erro)
usando o componente BentoBox, contadores de arquivos restaurados, lista
de arquivos pulados e opção de cópia para a Área de Trabalho.

Example:
    view = SummaryView()
    view.populate(copy_result)
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
)

from services.backup_copier import CopyResult, SkippedFile
from ui.components import BentoBox
from ui.format_utils import format_bytes as _format_bytes, format_time as _format_time


class SummaryView(QWidget):
    """Tela 5: restore outcome summary with skipped-files option.

    Example:
        v = SummaryView()
        v.populate(copy_result)
    """

    copy_skipped_requested = pyqtSignal()
    finish_requested = pyqtSignal()
    try_other_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(14)

        layout.addStretch()
        self._init_outcome_section(layout)
        layout.addSpacing(6)
        self._init_metrics_section(layout)
        self._init_skipped_section(layout)
        layout.addStretch()
        self._init_navigation_section(layout)

    def _init_outcome_section(self, layout: QVBoxLayout) -> None:
        self._outcome_title = QLabel("INICIALIZANDO")
        self._outcome_title.setObjectName("ViewTitle")
        self._outcome_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._outcome_title)

        self._outcome_subtitle = QLabel("")
        self._outcome_subtitle.setObjectName("ViewSubtitle")
        self._outcome_subtitle.setAlignment(Qt.AlignCenter)
        self._outcome_subtitle.setWordWrap(True)
        layout.addWidget(self._outcome_subtitle)

    def _init_metrics_section(self, layout: QVBoxLayout) -> None:
        self._metrics_layout = QHBoxLayout()
        self._metrics_layout.setSpacing(12)
        self._files_card = BentoBox("ARQUIVOS RESTAURADOS", "0", "Copiados com sucesso")
        self._bytes_card = BentoBox("VOLUME TRANSFERIDO", "0 B", "Tamanho consolidado")
        self._time_card = BentoBox("TEMPO DE OPERAÇÃO", "--", "Tempo total decorrido")

        card_width = 180
        self._files_card.setFixedWidth(card_width)
        self._bytes_card.setFixedWidth(card_width)
        self._time_card.setFixedWidth(card_width)

        self._metrics_layout.addStretch()
        self._metrics_layout.addWidget(self._files_card)
        self._metrics_layout.addWidget(self._bytes_card)
        self._metrics_layout.addWidget(self._time_card)
        self._metrics_layout.addStretch()
        layout.addLayout(self._metrics_layout)

    def _init_skipped_section(self, layout: QVBoxLayout) -> None:
        self._skipped_frame = QFrame()
        self._skipped_frame.setObjectName("BentoCard")
        self._skipped_frame.setVisible(False)
        skipped_layout = QVBoxLayout(self._skipped_frame)
        skipped_layout.setContentsMargins(16, 12, 16, 12)
        skipped_layout.setSpacing(6)

        self._skipped_title = QLabel()
        self._skipped_title.setObjectName("BentoTitle")
        skipped_layout.addWidget(self._skipped_title)

        self._setup_skipped_scroll(skipped_layout)
        self._setup_skipped_btn(skipped_layout)
        layout.addWidget(self._skipped_frame)

    def _setup_skipped_scroll(self, layout: QVBoxLayout) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
        self._skipped_list = QWidget()
        self._skipped_list_layout = QVBoxLayout(self._skipped_list)
        self._skipped_list_layout.setAlignment(Qt.AlignTop)
        self._skipped_list_layout.setSpacing(2)
        self._skipped_list_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self._skipped_list)
        layout.addWidget(scroll)

    def _setup_skipped_btn(self, layout: QVBoxLayout) -> None:
        self._copy_skipped_btn = QPushButton("Copiar pulados para a Área de Trabalho")
        self._copy_skipped_btn.setObjectName("SecondaryButton")
        self._copy_skipped_btn.setCursor(Qt.PointingHandCursor)
        self._copy_skipped_btn.clicked.connect(self._on_copy_skipped)
        layout.addWidget(self._copy_skipped_btn)

        self._copy_feedback = QLabel()
        self._copy_feedback.setObjectName("BentoSub")
        self._copy_feedback.setVisible(False)
        layout.addWidget(self._copy_feedback)

    def _init_navigation_section(self, layout: QVBoxLayout) -> None:
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        self._try_other_btn = QPushButton("Tentar outra coisa")
        self._try_other_btn.setObjectName("SecondaryButton")
        self._try_other_btn.setCursor(Qt.PointingHandCursor)
        self._try_other_btn.clicked.connect(self.try_other_requested.emit)
        self._try_other_btn.setVisible(False)
        btn_row.addWidget(self._try_other_btn)

        self._finish_btn = QPushButton("Concluir")
        self._finish_btn.setObjectName("PrimaryButton")
        self._finish_btn.setCursor(Qt.PointingHandCursor)
        self._finish_btn.clicked.connect(self.finish_requested.emit)
        btn_row.addWidget(self._finish_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, result: CopyResult, admin_mode: bool = False) -> None:
        """Fill in the summary with the copy result.

        Example:
            view.populate(copy_result)
        """
        self._set_outcome_display(result)
        self._set_skipped_section(result)
        self._try_other_btn.setVisible(admin_mode)

    def on_skipped_copy_done(self, success: bool, message: str) -> None:
        """Called when CopySkippedWorker finishes.

        Example:
            view.on_skipped_copy_done(True, "Desktop\\Remos - Arquivos Pulados")
        """
        self._copy_skipped_btn.setEnabled(True)
        self._copy_feedback.setVisible(True)
        if success:
            self._copy_feedback.setText(f"Copiado para {message}")
            self._copy_feedback.setStyleSheet("color: #27AE60; font-weight: bold; background: transparent;")
        else:
            self._copy_feedback.setText(f"Erro: {message}")
            self._copy_feedback.setStyleSheet("color: #C0392B; font-weight: bold; background: transparent;")

    # ------------------------------------------------------------------
    # Internal Handlers
    # ------------------------------------------------------------------

    def _set_outcome_display(self, result: CopyResult) -> None:
        """Set outcome header and simple metrics cards based on result."""
        self._files_card.update_content(
            title="ARQUIVOS RESTAURADOS",
            value=f"{result.files_copied} arquivos",
            subtitle="Copiados com sucesso",
        )
        self._bytes_card.update_content(
            title="VOLUME TRANSFERIDO",
            value=_format_bytes(result.bytes_copied),
            subtitle="Tamanho consolidado",
        )
        self._time_card.update_content(
            title="TEMPO DE OPERAÇÃO",
            value=_format_time(result.duration_seconds),
            subtitle="Tempo total decorrido",
        )
        self._update_outcome_header(result)

    def _update_outcome_header(self, result: CopyResult) -> None:
        """Update header text and color based on copy result.

        The title reflects how many files actually made it, not just the
        internal success flag: e.g. 911 copied + 4 failed is a partial
        success, not a failure — "RESTAURAÇÃO FALHOU" is reserved for runs
        where nothing was restored at all.
        """
        from ui.assets import RM_GREEN, RM_RED, RM_YELLOW
        n_issues = len(result.skipped_files) + len(result.failed_files)
        if result.cancelled:
            self._set_header_lbl("RESTAURAÇÃO CANCELADA", RM_RED, "A cópia foi cancelada pelo usuário.")
        elif result.files_copied == 0:
            self._set_header_lbl("RESTAURAÇÃO FALHOU", RM_RED, "Nenhum arquivo pôde ser restaurado.")
        elif n_issues:
            suffix = "arquivo pulado" if n_issues == 1 else "arquivos pulados"
            self._set_header_lbl(
                "SUCESSO PARCIAL", RM_YELLOW,
                f"{result.files_copied} arquivos restaurados, {n_issues} {suffix}.",
            )
        else:
            self._set_header_lbl("SUCESSO", RM_GREEN, "Todos os arquivos recuperados com sucesso!")

    def _set_header_lbl(self, title: str, color: str, sub: str) -> None:
        """Helper to apply text and stylesheet color to header labels."""
        self._outcome_title.setText(title)
        self._outcome_title.setStyleSheet(
            f"color: {color}; font-size: 32px; font-weight: bold; background: transparent;"
        )
        self._outcome_subtitle.setText(sub)

    def _set_skipped_section(self, result: CopyResult) -> None:
        """Build the skipped files list if any."""
        all_skipped = result.skipped_files + result.failed_files
        if not all_skipped:
            self._skipped_frame.setVisible(False)
            return

        self._skipped_frame.setVisible(True)
        self._skipped_title.setText(f"{len(all_skipped)} arquivos pulados")
        self._rebuild_skipped_list(all_skipped)
        self._copy_feedback.setVisible(False)

    def _rebuild_skipped_list(self, all_skipped: list[SkippedFile]) -> None:
        while self._skipped_list_layout.count():
            item = self._skipped_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for sf in all_skipped:
            lbl = QLabel(f"• {sf.source.name} — {sf.reason}")
            lbl.setObjectName("BentoSub")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background: transparent;")
            self._skipped_list_layout.addWidget(lbl)

    def _on_copy_skipped(self) -> None:
        self._copy_skipped_btn.setEnabled(False)
        self._copy_skipped_btn.setText("Copiando...")
        self.copy_skipped_requested.emit()
