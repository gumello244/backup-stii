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
    QPushButton, QCheckBox, QScrollArea, QFrame, QSizePolicy,
)

from config import DISK_OVERHEAD_FACTOR, DISK_OVERHEAD_BUFFER_BYTES, LOCAL_SPEED_FALLBACK_BPS
from services.backup_merger import (
    MergedFileSet, FolderSummary, MergedFile, is_raiz_file, filter_files_by_selection,
)
from ui.assets import (
    RM_TEXT_MUTED, RM_HERO_BG, RM_HERO_BORDER,
    RM_SURFACE, RM_BORDER, RM_GREEN, RM_RED,
)
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
    "RAIZ": "RAIZ",
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
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._setup_layout(pt_name, file_count, total_bytes)
        self.update_style()

    def _setup_layout(self, pt_name: str, file_count: int, total_bytes: int) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(self)
        self.checkbox.setObjectName("FolderOptionCheckbox")
        self.checkbox.setChecked(True)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setFixedWidth(12)
        self.checkbox.stateChanged.connect(self.update_style)

        self.title_lbl = QLabel(pt_name, self)
        self.title_lbl.setObjectName("FolderTitleLabel")

        suffix = "arquivo" if file_count == 1 else "arquivos"
        self.count_lbl = QLabel(f"{file_count} {suffix}", self)
        self.count_lbl.setObjectName("FolderCountLabel")

        self.size_lbl = QLabel(_format_bytes(total_bytes), self)
        self.size_lbl.setObjectName("FolderSizeLabel")

        layout.addWidget(self.checkbox)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.count_lbl)
        layout.addStretch()
        layout.addWidget(self.size_lbl)

    def update_style(self) -> None:
        if self.checkbox.isChecked():
            self.setStyleSheet(f"""
                FolderOptionWidget {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                FolderOptionWidget {{
                    background-color: {RM_SURFACE};
                    border: 1px solid {RM_BORDER};
                    border-radius: 6px;
                }}
                FolderOptionWidget:hover {{ border-color: #bbbbbb; }}
            """)

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
        self._admin_mode_flag: bool = False
        self._init_ui()
        self._options_card.hide()

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
            title="ESPAÇO EM DISCO",
            value="Verificando...",
            subtitle="",
            variant="hero",
            parent=self,
        )
        self._time_card = BentoBox(
            title="ESTIMATIVA DE TEMPO",
            value="--",
            subtitle="Estimativa de transferência",
            variant="default",
            parent=self,
        )

        # Options Bento Box card (below Time Card)
        self._options_card = QFrame(self)
        self._options_card.setObjectName("SurfaceCard")
        self._options_card.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px;"
            f" background: #FFFFFF; }}"
        )
        options_layout = QVBoxLayout(self._options_card)
        options_layout.setContentsMargins(16, 10, 16, 10)
        options_layout.setSpacing(10)

        options_title = QLabel("OPÇÕES DE RESTAURAÇÃO", self._options_card)
        options_title.setObjectName("BentoTitle")
        options_title.setStyleSheet(f"font-size: 10px; font-weight: 800; color: {RM_TEXT_MUTED}; letter-spacing: 1px;")

        self.cut_checkbox = QCheckBox("Recortar arquivos", self._options_card)
        self.cut_checkbox.setCursor(Qt.PointingHandCursor)
        self.cut_checkbox.setStyleSheet("""
            QCheckBox {
                font-size: 12px;
                font-weight: 400;
                color: #4A5568;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 12px;
                height: 12px;
            }
        """)

        options_layout.addWidget(options_title)
        options_layout.addWidget(self.cut_checkbox)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        left_column.addWidget(self._hero_card)
        left_column.addWidget(self._time_card)
        left_column.addWidget(self._options_card)
        left_column.addStretch()

        # Folder selection bento card (Right Column)
        self._folder_card = QFrame(self)
        self._folder_card.setObjectName("SurfaceCard")
        self._folder_card.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px;"
            f" background: #FFFFFF; }}"
        )
        self._folder_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        folder_card_layout = QVBoxLayout(self._folder_card)
        folder_card_layout.setContentsMargins(0, 12, 0, 12)
        folder_card_layout.setSpacing(6)

        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(16, 0, 16, 0)
        folder_title = QLabel("SELECIONAR PASTAS", self._folder_card)
        folder_title.setObjectName("BentoTitle")
        title_layout.addWidget(folder_title)
        folder_card_layout.addLayout(title_layout)

        # Scrollable folder list
        scroll = QScrollArea(self)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._folder_container = QWidget(scroll)
        self._folder_container.setStyleSheet("background: transparent;")
        self._folder_layout = QVBoxLayout(self._folder_container)
        self._folder_layout.setAlignment(Qt.AlignTop)
        self._folder_layout.setSpacing(4)
        self._folder_layout.setContentsMargins(16, 0, 16, 0)
        scroll.setWidget(self._folder_container)
        folder_card_layout.addWidget(scroll, stretch=1)

        # Main horizontal columns layout (Left Column takes 1, Right Column takes 2 for more width)
        right_column = QVBoxLayout()
        right_column.setContentsMargins(0, 0, 0, 0)
        right_column.setSpacing(0)
        right_column.addWidget(self._folder_card, stretch=1)

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

    def populate(self, merged: MergedFileSet, admin_mode: bool = False, is_local: bool = True) -> None:
        """Fill in the view with data from a resolved MergedFileSet.

        Example:
            view.populate(merged_file_set)
        """
        self._merged = merged
        self._admin_mode_flag = admin_mode
        if admin_mode and is_local:
            self._options_card.show()
        else:
            self._options_card.hide()
            self.cut_checkbox.setChecked(False)
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
        if self._is_admin_mode():
            group_count = self._build_admin_grouped_folder_list()
        else:
            group_count = 0
            for key, title, summary in self._folder_groups_by_folder():
                self._add_folder_checkbox(key, title, summary)
        min_height = 146
        calculated_height = 54 + len(self._checkboxes) * 36 + group_count * 24
        target_height = max(calculated_height, min_height)
        self._folder_card.setMinimumHeight(min_height)
        self._folder_card.setMaximumHeight(16777215)

    def _is_admin_mode(self) -> bool:
        return self._admin_mode_flag

    def _folder_groups_by_folder(self) -> list[tuple[str, str, FolderSummary]]:
        """Group files by folder name for normal-mode restores."""
        if not self._merged:
            return []

        groups: dict[str, FolderSummary] = {}
        titles: dict[str, str] = {}
        for mf in self._merged.files:
            key = self._selection_key_for_file(mf)
            summary = groups.get(key)
            if summary is None:
                summary = FolderSummary(file_count=0, total_bytes=0)
                groups[key] = summary
                titles[key] = self._selection_title_for_file(mf)
            summary.file_count += 1
            summary.total_bytes += mf.size_bytes

        return [
            (key, titles[key], groups[key])
            for key in sorted(groups)
        ]

    def _selection_key_for_file(self, mf: MergedFile) -> str:
        if mf.target_profile:
            return f"{mf.target_profile}::{mf.dest_folder}"
        return mf.dest_folder

    def _selection_title_for_file(self, mf: MergedFile) -> str:
        return _FOLDER_NAME_MAP_PT.get(mf.dest_folder, mf.dest_folder)

    def _build_admin_grouped_folder_list(self) -> int:
        """Build restore rows grouped by source profile/root for admin mode."""
        grouped_rows = self._folder_groups_by_source()
        for source_key, source_title, rows in grouped_rows:
            group_card = QFrame(self._folder_container)
            group_card.setStyleSheet("QFrame { border: none; background: transparent; }")
            group_layout = QVBoxLayout(group_card)
            group_layout.setContentsMargins(0, 4, 0, 4)
            group_layout.setSpacing(4)

            source_lbl = QLabel(source_title, group_card)
            source_lbl.setObjectName("FolderGroupLabel")
            source_lbl.setStyleSheet(
                f"font-size: 10px; font-weight: 800; color: {RM_TEXT_MUTED};"
                " letter-spacing: 1px; background: transparent; border: none;"
            )
            group_layout.addWidget(source_lbl)

            for row_key, row_title, summary in rows:
                row = self._create_folder_row(row_key, row_title, summary)
                group_layout.addWidget(row)

            self._folder_layout.addWidget(group_card)
        return len(grouped_rows)

    def _folder_groups_by_source(self) -> list[tuple[str, str, list[tuple[str, str, FolderSummary]]]]:
        """Group files by source root so admin restores stay separated."""
        if not self._merged:
            return []

        grouped: dict[str, dict[str, FolderSummary]] = {}
        titles: dict[str, str] = {}
        from services.backup_discovery import detect_user_login
        current_user = detect_user_login()

        for mf in self._merged.files:
            if mf.target_profile:
                source_key = mf.target_profile
                display_title = mf.target_profile
                row_key = f"{mf.target_profile}::{mf.dest_folder}"
                row_title = _FOLDER_NAME_MAP_PT.get(mf.dest_folder, mf.dest_folder)
            elif is_raiz_file(mf):
                source_key = "raiz"
                display_title = "RAIZ"
                # Determine subfolder inside RAIZ
                parts = mf.relative_name.split("/")
                sub_folder = parts[0] if len(parts) > 1 else "RAIZ"
                row_key = f"raiz::{sub_folder}"
                row_title = _FOLDER_NAME_MAP_PT.get(sub_folder, sub_folder)
            else:
                source_key = current_user
                display_title = current_user
                row_key = mf.dest_folder
                row_title = _FOLDER_NAME_MAP_PT.get(mf.dest_folder, mf.dest_folder)

            titles.setdefault(source_key, display_title)

            source_rows = grouped.setdefault(source_key, {})
            summary = source_rows.get(row_key)
            if summary is None:
                summary = FolderSummary(file_count=0, total_bytes=0)
                source_rows[row_key] = summary
            summary.file_count += 1
            summary.total_bytes += mf.size_bytes

        ordered: list[tuple[str, str, list[tuple[str, str, FolderSummary]]]] = []
        for source_key in sorted(grouped, key=lambda k: (k != "raiz", k)):
            rows: list[tuple[str, str, FolderSummary]] = []
            for row_key, summary in sorted(grouped[source_key].items()):
                if "::" in row_key:
                    profile, folder = row_key.split("::", 1)
                    row_title = _FOLDER_NAME_MAP_PT.get(folder, folder)
                else:
                    row_title = _FOLDER_NAME_MAP_PT.get(row_key, row_key)
                rows.append((row_key, row_title, summary))
            ordered.append((source_key, titles[source_key], rows))
        return ordered

    def _clear_folder_layout(self) -> None:
        """Clear all child widgets inside the folder layout."""
        while self._folder_layout.count():
            item = self._folder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_folder_row(self, key: str, title: str, summary: FolderSummary) -> FolderOptionWidget:
        row = FolderOptionWidget(title, summary.file_count, summary.total_bytes)
        row.checkbox.stateChanged.connect(self._recalculate)
        self._checkboxes[key] = row.checkbox
        return row

    def _add_folder_checkbox(self, key: str, title: str, summary: FolderSummary) -> None:
        """Create and add a checkbox for a single backup folder."""
        row = self._create_folder_row(key, title, summary)
        self._folder_layout.addWidget(row)

    def _selected_folders(self) -> list[str]:
        """Return the names of all currently checked folders."""
        return [
            name for name, cb in self._checkboxes.items() if cb.isChecked()
        ]

    def _selected_files(self) -> list[MergedFile]:
        """Return a list of MergedFile objects that belong to selected folders."""
        if not self._merged:
            return []
        return filter_files_by_selection(self._merged.files, self._selected_folders())

    def _recalculate(self) -> None:
        """Update requirements status based on selection and disk safety margin."""
        selected = self._selected_files()
        needed = sum(f.size_bytes for f in selected)
        available = self._get_available_space()

        from services.copy_benchmark import estimate_copy_seconds_for_files
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
        self._time_card.update_content(
            title="ESTIMATIVA DE TEMPO",
            value=_format_time(time_est),
            subtitle="Estimativa de transferência",
        )

        drive_letter = Path.home().drive
        variant = "success" if enough else "danger"
        self._hero_card.set_variant(variant)

        if not self._is_admin_mode():
            self._hero_card.update_content(
                title="ESPAÇO EM DISCO",
                value="Suficiente" if enough else "Insuficiente",
                subtitle=f"{_format_bytes(needed)} necessários",
            )
            val_color = RM_GREEN if enough else RM_RED
            self._hero_card._val_lbl.setStyleSheet(
                f"font-size: 32px; font-weight: 800; letter-spacing: -1px; color: {val_color}; background: transparent;"
            )
            self._hero_card._sub_lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; background: transparent;")
        else:
            self._hero_card.update_content(
                title="ESPAÇO NECESSÁRIO",
                value=_format_bytes(needed),
                subtitle=f"{_format_bytes(available)} livre em {drive_letter}\\",
            )
            val_color = RM_GREEN if enough else RM_RED
            self._hero_card._val_lbl.setStyleSheet(
                f"font-size: 32px; font-weight: 800; letter-spacing: -1px; color: {val_color}; background: transparent;"
            )
            self._hero_card._sub_lbl.setStyleSheet(f"color: {RM_TEXT_MUTED}; background: transparent;")

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
