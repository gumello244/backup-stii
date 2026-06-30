from __future__ import annotations

"""Tela 3 — Requisitos & Confirmação.

Apresenta os requisitos de espaço em disco, a estimativa de tempo e uma
lista de caixas de seleção no nível de pasta. O botão "Restaurar" é
bloqueado se houver espaço em disco insuficiente ou nenhuma pasta selecionada.

Example:
    view = ConfirmView()
    view.populate(merged_file_set)
    view.restore_requested.connect(handle_restore)
"""
import shutil
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QScrollArea, QFrame,
)

from config import DISK_OVERHEAD_FACTOR, DISK_OVERHEAD_BUFFER_BYTES, LOCAL_SPEED_FALLBACK_BPS
from services.backup_merger import MergedFileSet, FolderSummary, MergedFile
from ui.components import BentoBox
from ui.format_utils import format_bytes as _format_bytes, format_time as _format_time

from PyQt5.QtGui import QMouseEvent

_FOLDER_NAME_MAP_PT: dict[str, str] = {
    "Desktop": "Área de Trabalho",
    "Documents": "Documentos",
    "Downloads": "Downloads",
    "Pictures": "Imagens",
    "Music": "Músicas",
    "Videos": "Vídeos",
    "Favorites": "Favoritos",
}


class FolderOptionWidget(QFrame):
    """Custom row widget representing a folder choice.

    Displays the checkbox indicator, folder title, file count, and folder size
    aligned in a single line with custom styles.
    """

    def __init__(
        self,
        pt_name: str,
        file_count: int,
        total_bytes: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FolderOptionRow")
        self.setCursor(Qt.PointingHandCursor)
        self._setup_layout(pt_name, file_count, total_bytes)

    def _setup_layout(self, pt_name: str, file_count: int, total_bytes: int) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(4)

        self.checkbox = QCheckBox(self)
        self.checkbox.setObjectName("FolderOptionCheckbox")
        self.checkbox.setChecked(True)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setFixedWidth(12)

        self.title_lbl = QLabel(pt_name, self)
        self.title_lbl.setObjectName("FolderTitleLabel")

        suffix = "arquivo" if file_count == 1 else "arquivos"
        self.count_lbl = QLabel(f"({file_count} {suffix})", self)
        self.count_lbl.setObjectName("FolderCountLabel")

        self.size_lbl = QLabel(_format_bytes(total_bytes), self)
        self.size_lbl.setObjectName("FolderSizeLabel")

        layout.addWidget(self.checkbox)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.count_lbl)
        layout.addStretch()
        layout.addWidget(self.size_lbl)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Toggle checkbox state on click anywhere on the widget."""
        self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


class ConfirmView(QWidget):
    """Tela 3: requirements display + folder selection + restore button using Bento Grid.

    Example:
        v = ConfirmView()
        v.restore_requested.connect(on_restore)
    """

    restore_requested = pyqtSignal(list)  # list[str] selected folder names
    back_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._merged: MergedFileSet | None = None
        self._checkboxes: dict[str, QCheckBox] = {}
        self._write_speed_bps: Optional[int] = None
        self._network_speed_bps: Optional[int] = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("Confirmação", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        self._subtitle = QLabel("Selecione as pastas e confirme os requisitos de espaço.", self)
        self._subtitle.setObjectName("ViewSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        # Bento cards (Left Column stack)
        self._hero_card = BentoBox(
            title="ESPAÇO DISCO",
            value="Verificando...",
            subtitle="",
            variant="default",
            parent=self,
        )
        self._needed_card = BentoBox(
            title="ESPAÇO NECESSÁRIO",
            value="--",
            subtitle="Arquivos selecionados",
            variant="default",
            parent=self,
        )
        self._time_card = BentoBox(
            title="ESTIMATIVA DE TEMPO",
            value="--",
            subtitle="Estimativa de transferência",
            variant="default",
            parent=self,
        )

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        left_column.addWidget(self._hero_card)
        left_column.addWidget(self._needed_card)
        left_column.addWidget(self._time_card)

        # Folder selection bento card (Right Column)
        self._folder_card = QFrame(self)
        self._folder_card.setObjectName("BentoCard")
        folder_card_layout = QVBoxLayout(self._folder_card)
        folder_card_layout.setContentsMargins(16, 12, 16, 12)
        folder_card_layout.setSpacing(6)

        folder_title = QLabel("SELECIONAR PASTAS", self._folder_card)
        folder_title.setObjectName("BentoTitle")
        folder_card_layout.addWidget(folder_title)

        # Scrollable folder list
        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        self._folder_container = QWidget(scroll)
        self._folder_container.setStyleSheet("background: transparent;")
        self._folder_layout = QVBoxLayout(self._folder_container)
        self._folder_layout.setAlignment(Qt.AlignTop)
        self._folder_layout.setSpacing(4)
        self._folder_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._folder_container)
        folder_card_layout.addWidget(scroll, stretch=1)

        # Main horizontal columns layout (Left Column takes 1, Right Column takes 2 for more width)
        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(0)
        right_column.addWidget(self._folder_card)
        right_column.addStretch(1)

        main_columns = QHBoxLayout()
        main_columns.setSpacing(12)
        main_columns.addLayout(left_column, stretch=2)
        main_columns.addLayout(right_column, stretch=3)

        layout.addLayout(main_columns, stretch=1)

        # Navigation buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)

        self._restore_btn = QPushButton("Começar restauração de backup", self)
        self._restore_btn.setObjectName("PrimaryButton")
        self._restore_btn.setCursor(Qt.PointingHandCursor)
        self._restore_btn.setEnabled(False)
        self._restore_btn.clicked.connect(self._on_restore_clicked)

        # Place buttons side-by-side and centered at the bottom of the window
        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._restore_btn)
        btn_row.addStretch()

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(self, merged: MergedFileSet) -> None:
        """Fill in the view with data from a resolved MergedFileSet.

        Example:
            view.populate(merged_file_set)
        """
        self._merged = merged
        self._build_folder_list()
        self._recalculate()

    def set_benchmarked_speeds(self, local_speed: float, network_speed: float) -> None:
        """Receive pre-calculated benchmark speeds from the background thread."""
        self._write_speed_bps = int(local_speed)
        self._network_speed_bps = int(network_speed)
        if self._merged:
            self._recalculate()

    # ------------------------------------------------------------------
    # Internal Layout & Calculation Logic
    # ------------------------------------------------------------------

    def _build_folder_list(self) -> None:
        """Create one checkbox per destination folder."""
        self._clear_folder_layout()
        self._checkboxes.clear()
        for name, summary in sorted(self._merged.by_folder.items()):
            self._add_folder_checkbox(name, summary)
        min_height = 146
        calculated_height = 54 + len(self._checkboxes) * 32
        target_height = max(calculated_height, min_height)
        self._folder_card.setMinimumHeight(min_height)
        self._folder_card.setMaximumHeight(min(target_height, 280))



    def _clear_folder_layout(self) -> None:
        """Clear all child widgets inside the folder layout."""
        while self._folder_layout.count():
            item = self._folder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_folder_checkbox(self, name: str, summary: FolderSummary) -> None:
        """Create and add a checkbox for a single backup folder."""
        pt_name = _FOLDER_NAME_MAP_PT.get(name, name)
        row = FolderOptionWidget(pt_name, summary.file_count, summary.total_bytes)
        row.checkbox.stateChanged.connect(self._recalculate)
        self._folder_layout.addWidget(row)
        self._checkboxes[name] = row.checkbox

    def _selected_folders(self) -> list[str]:
        """Return the names of all currently checked folders."""
        return [
            name for name, cb in self._checkboxes.items() if cb.isChecked()
        ]

    def _selected_files(self) -> list[MergedFile]:
        """Return a list of MergedFile objects that belong to selected folders."""
        if not self._merged:
            return []
        selected_dirs = set(self._selected_folders())
        return [f for f in self._merged.files if f.dest_folder in selected_dirs]

    def _recalculate(self) -> None:
        """Update requirements status based on selection and disk safety margin."""
        selected = self._selected_files()
        needed = sum(f.size_bytes for f in selected)
        available = self._get_available_space()

        from services.backup_copier import estimate_copy_seconds_for_files
        write_sp = self._write_speed_bps or LOCAL_SPEED_FALLBACK_BPS
        time_est = estimate_copy_seconds_for_files(
            selected, write_sp, self._network_speed_bps
        )

        needed_with_overhead = int(needed * DISK_OVERHEAD_FACTOR) + DISK_OVERHEAD_BUFFER_BYTES
        enough = available >= needed_with_overhead
        has_selection = len(self._selected_folders()) > 0

        self._update_labels(needed, available, time_est, enough)
        self._restore_btn.setEnabled(enough and has_selection)

    def _update_labels(
        self, needed: int, available: int, time_est: int, enough: bool
    ) -> None:
        """Update requirements and status bento cards."""
        self._needed_card.update_content(
            title="ESPAÇO NECESSÁRIO",
            value=_format_bytes(needed),
            subtitle="Arquivos selecionados",
        )
        self._time_card.update_content(
            title="ESTIMATIVA DE TEMPO",
            value=_format_time(time_est),
            subtitle="Estimativa de transferência",
        )

        drive_letter = Path.home().drive
        if enough:
            self._hero_card.update_content(
                title="ESPAÇO DISCO",
                value="Suficiente",
                subtitle=f"{_format_bytes(available)} livre em {drive_letter}\\",
            )
            self._hero_card.set_variant("success")
            return

        self._hero_card.update_content(
            title="ESPAÇO DISCO",
            value="Insuficiente",
            subtitle=f"Falta espaço em {drive_letter}\\",
        )
        self._hero_card.set_variant("danger")

    def _get_available_space(self) -> int:
        """Free disk space on the user's home drive."""
        try:
            usage = shutil.disk_usage(Path.home().drive + "\\")
            return usage.free
        except OSError:
            return 0

    def _select_all(self) -> None:
        for cb in self._checkboxes.values():
            cb.setChecked(True)

    def _deselect_all(self) -> None:
        for cb in self._checkboxes.values():
            cb.setChecked(False)

    def _on_restore_clicked(self) -> None:
        selected = self._selected_folders()
        if selected:
            self.restore_requested.emit(selected)
