from __future__ import annotations

"""AdminCreateBackupView & AdminCreateBackupConfigView — configure and execute local backups.

Allows the admin to select sources (profiles, drives) on the left pane, exclusions,
and select folders to back up on the right pane. Moves OS/Destination target configurations
to the next config view. Shows live size and time estimates instantly using in-memory file cache.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QRadioButton, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QButtonGroup, QSizePolicy
)
from PyQt5.QtGui import QMouseEvent, QIntValidator

from ui.assets import (
    RM_BORDER, RM_TEXT_MUTED, RM_SURFACE, RM_ACCENT,
    RM_HERO_BG, RM_HERO_BORDER
)
from ui.components import BentoBox
from ui.format_utils import format_bytes as _format_bytes, format_time as _format_time
from ui.views.admin_restore_cards import SkeletonCard
from services.admin_backup_discovery import (
    get_local_user_profiles, get_local_drives,
    _walk_stats_recursive, PENDING_STATS, ERROR_STATS
)
from services.backup_discovery import get_local_drives as get_drives_fallback, _safe_mtime, detect_user_login
from services.backup_merger import MergedFile
from services.copy_benchmark import estimate_copy_seconds_for_files
from ui.workers import CreateOSWorker, BenchmarkWorker
from config import get_server_config

logger = logging.getLogger(__name__)

# Standard user folders mapped for backup (supporting list of paths for grouping)
_PROFILE_SUBFOLDERS = [
    ("Contatos", "Contacts"),
    ("Área de Trabalho", "Desktop"),
    ("Documentos", "Documents"),
    ("Downloads", "Downloads"),
    ("Imagens", "Pictures"),
    ("Músicas", "Music"),
    ("Vídeos", "Videos"),
    ("Favoritos Chrome", "AppData/Local/Google/Chrome/User Data/Default/Bookmarks"),
    ("Favoritos Edge", "AppData/Local/Microsoft/Edge/User Data/Default/Bookmarks"),
    ("Firefox", "AppData/Roaming/Mozilla/Firefox"),
    ("Notas Autodesivas", ["AppData/Roaming/Microsoft/Sticky Notes", "AppData/Local/Packages/Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe"]),
    ("Outlook", ["AppData/Local/Microsoft/Outlook", "AppData/Roaming/Microsoft/Outlook"]),
    ("Outlook Assinaturas", "AppData/Roaming/Microsoft/Assinaturas"),
]

# Root system folders to exclude under C:\
_SYSTEM_ROOT_FOLDERS = {
    "arquivos de programas", "arquivos de programas (x86)", "program files",
    "program files (x86)", "inetpub", "intel", "dell", "msocache", "perflogs",
    "programdata", "temp", "users", "windows", "recovery", "system volume information",
    "$recycle.bin", "config.msi", "documents and settings", "$winreagent", "boot",
    "efi", "pagefile.sys", "swapfile.sys", "hiberfil.sys", "dumpstack.log",
    "tmp", "nvidia"
}


class LocalSourceDetailWorker(QThread):
    """Background worker to calculate sizes and modified times for discovered local sources."""
    stats_calculated = pyqtSignal(str, str, object, float)  # type, name, size_bytes (object to avoid overflow), modified_time
    finished = pyqtSignal()

    def __init__(self, sources: list[tuple[str, str, Path]]) -> None:
        super().__init__()
        self.sources = sources

    def run(self) -> None:
        try:
            for source_type, name, path in self.sources:
                total_bytes = 0
                max_mtime = 0.0

                if source_type == "profile":
                    for _, sub_paths in _PROFILE_SUBFOLDERS:
                        paths_list = [sub_paths] if isinstance(sub_paths, str) else sub_paths
                        for sub_rel in paths_list:
                            folder_path = path / sub_rel
                            if not folder_path.exists():
                                continue
                            b, _, _, mtime = _walk_stats_recursive(folder_path)
                            total_bytes += b
                            if mtime > max_mtime:
                                max_mtime = mtime
                    if max_mtime == 0.0:
                        max_mtime = _safe_mtime(path)
                else:
                    # Drive
                    try:
                        for entry in path.iterdir():
                            if entry.is_dir() and entry.name.lower() not in _SYSTEM_ROOT_FOLDERS:
                                b, _, _, mtime = _walk_stats_recursive(entry)
                                total_bytes += b
                                if mtime > max_mtime:
                                    max_mtime = mtime
                    except OSError:
                        pass
                    if max_mtime == 0.0:
                        max_mtime = _safe_mtime(path)

                self.stats_calculated.emit(source_type, name, total_bytes, max_mtime)

        except Exception as e:
            logger.error('{"event":"local_source_detail_worker_failed","error":"%s"}', e)
        finally:
            self.finished.emit()


class LocalSourceDetailScannerWorker(QThread):
    """Background worker to scan all file structures (unfiltered) of checked folders."""
    folder_scanned = pyqtSignal(Path, list)  # path, list[MergedFile]
    finished = pyqtSignal()

    def __init__(self, selections: list[tuple[str, Path, str]]) -> None:
        super().__init__()
        self._selections = selections

    def run(self) -> None:
        try:
            for item_type, folder_path, group_name in self._selections:
                if not folder_path.exists():
                    self.folder_scanned.emit(folder_path, [])
                    continue

                files = []
                if folder_path.is_file():
                    try:
                        st = folder_path.stat()
                        sz = st.st_size
                    except OSError:
                        self.folder_scanned.emit(folder_path, [])
                        continue

                    rel_name = folder_path.name
                    for display, sub_rel_or_list in _PROFILE_SUBFOLDERS:
                        paths_list = [sub_rel_or_list] if isinstance(sub_rel_or_list, str) else sub_rel_or_list
                        matched = False
                        for sub_rel in paths_list:
                            if folder_path.as_posix().endswith(sub_rel):
                                rel_name = sub_rel
                                matched = True
                                break
                        if matched:
                            break

                    files.append(MergedFile(
                        source_path=folder_path,
                        dest_folder=Path(rel_name).parent.as_posix() if "/" in rel_name else "AppData",
                        relative_name=Path(rel_name).name,
                        size_bytes=sz,
                        modified_time=st.st_mtime,
                        target_profile=group_name if item_type == 'profile_folder' else None,
                    ))
                    self.folder_scanned.emit(folder_path, files)
                    continue

                # Recursively walk directory to build all unfiltered MergedFile list
                try:
                    for root, _, filenames in os.walk(folder_path):
                        for filename in filenames:
                            if filename.lower() in ("desktop.ini", "thumbs.db", ".ds_store"):
                                continue

                            file_path = Path(root) / filename
                            try:
                                st = file_path.stat()
                                sz = st.st_size
                            except OSError:
                                continue

                            try:
                                rel_name = file_path.relative_to(folder_path).as_posix()
                            except ValueError:
                                rel_name = filename

                            if item_type == 'profile_folder':
                                dest_folder = folder_path.name
                                target_profile = group_name
                            else:
                                dest_folder = "RAIZ"
                                parent_folder_name = folder_path.name
                                rel_name = f"{parent_folder_name}/{rel_name}"
                                target_profile = None

                            files.append(MergedFile(
                                source_path=file_path,
                                dest_folder=dest_folder,
                                relative_name=rel_name,
                                size_bytes=sz,
                                modified_time=st.st_mtime,
                                target_profile=target_profile,
                            ))
                except OSError:
                    pass
                self.folder_scanned.emit(folder_path, files)
        except Exception as e:
            logger.error('{"event":"local_source_detail_scan_failed","error":"%s"}', e)
        finally:
            self.finished.emit()


class LocalSourceCard(QFrame):
    """Clickable card representing a local backup source (user profile or drive)."""
    clicked = pyqtSignal(object)  # LocalSourceCard

    def __init__(
        self,
        source_type: str,
        name: str,
        path: Path,
        size_bytes: int = PENDING_STATS,
        modified_time: float = 0.0,
        is_logged_in: bool = False,
        parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.source_type = source_type
        self.name = name
        self.path = path
        self.size_bytes = size_bytes
        self.modified_time = modified_time
        self.is_logged_in = is_logged_in
        self.selected = False
        self._build()

    def _build(self) -> None:
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        name_lbl = QLabel(self.name, self)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 12px; background: transparent; border: none; margin: 0px; padding: 0px;"
        )
        tag = "Perfil"
        if self.source_type == "drive":
            tag = "Disco"
        elif self.is_logged_in:
            tag = "Logado"
            
        tag_lbl = QLabel(tag, self)
        tag_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 10px; background: transparent; border: none;"
        )
        top_row.addWidget(name_lbl, 1)
        top_row.addWidget(tag_lbl)
        layout.addLayout(top_row)

        self._stats_lbl = QLabel(self._stats_text(), self)
        self._stats_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 11px; background: transparent; border: none; margin: 0px; padding: 0px;"
        )
        layout.addWidget(self._stats_lbl)

    def _stats_text(self) -> str:
        if self.size_bytes == PENDING_STATS:
            return "Calculando..."

        try:
            dt = datetime.fromtimestamp(self.modified_time)
            date_str = dt.strftime("%d/%m/%Y")
        except (ValueError, OSError, OverflowError):
            date_str = "--/--/----"

        return f"{_format_bytes(self.size_bytes)} • {date_str}"

    def update_stats(self, size_bytes: int, modified_time: float) -> None:
        self.size_bytes = size_bytes
        self.modified_time = modified_time
        self._stats_lbl.setText(self._stats_text())

    def update_style(self) -> None:
        # Constant 2px border width prevents layout shifts or cards jumping when clicked
        if self.selected:
            self.setStyleSheet(f"""
                LocalSourceCard {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                LocalSourceCard {{
                    background-color: {RM_SURFACE};
                    border: 2px solid {RM_BORDER};
                    border-radius: 8px;
                }}
                LocalSourceCard:hover {{ background-color: #EDF2F7; }}
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self)
        super().mousePressEvent(event)


class LocalFolderOptionWidget(QFrame):
    """Row widget representing a checkable folder, matching confirm view options design."""
    toggled = pyqtSignal()

    def __init__(
        self,
        display_name: str,
        path: Path | list[Path],
        item_type: str,
        profile: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.display_name = display_name
        self.path = path
        self.item_type = item_type
        self.profile = profile
        self.selected = True
        self.file_count = PENDING_STATS
        self.size_bytes = 0

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._setup_layout()
        self.update_style()

    def _setup_layout(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(self)
        self.checkbox.setObjectName("FolderOptionCheckbox")
        self.checkbox.setChecked(True)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setFixedWidth(18)
        self.checkbox.stateChanged.connect(self._on_checkbox_toggled)

        self.title_lbl = QLabel(self.display_name, self)
        self.title_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 600; color: #1A202C; background: transparent; border: none;"
        )

        self.count_lbl = QLabel("Calculando...", self)
        self.count_lbl.setStyleSheet(
            f"font-size: 11px; color: {RM_TEXT_MUTED}; background: transparent; border: none;"
        )

        self.size_lbl = QLabel("", self)
        self.size_lbl.setStyleSheet(
            f"font-size: 12px; font-weight: bold; color: {RM_ACCENT}; background: transparent; border: none;"
        )

        layout.addWidget(self.checkbox)
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.count_lbl)
        layout.addStretch()
        layout.addWidget(self.size_lbl)

    def _on_checkbox_toggled(self) -> None:
        self.selected = self.checkbox.isChecked()
        self.update_style()
        self.toggled.emit()

    def update_style(self) -> None:
        if self.checkbox.isChecked():
            self.setStyleSheet(f"""
                LocalFolderOptionWidget {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                LocalFolderOptionWidget {{
                    background-color: {RM_SURFACE};
                    border: 1px solid {RM_BORDER};
                    border-radius: 6px;
                }}
                LocalFolderOptionWidget:hover {{ border-color: #bbbbbb; }}
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)

    def set_stats(self, file_count: int, size_bytes: int) -> None:
        self.file_count = file_count
        self.size_bytes = size_bytes

        if file_count == ERROR_STATS:
            self.count_lbl.setText("Erro")
            self.size_lbl.setText("")
        else:
            suffix = "arquivo" if file_count == 1 else "arquivos"
            self.count_lbl.setText(f"{file_count} {suffix}")
            self.size_lbl.setText(_format_bytes(size_bytes))


class AdminCreateBackupView(QWidget):
    """View to select local folders and trigger continuation configuration."""

    back_requested = pyqtSignal()
    continue_requested = pyqtSignal(list, bool)  # list[MergedFile], skip_media_exec

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_files: list[MergedFile] = []
        self._total_bytes: int = 0
        self._write_speed: int = 50_000_000
        
        self._discovery_worker: Optional[LocalSourceDetailWorker] = None
        self._detail_scanner_worker: Optional[LocalSourceDetailScannerWorker] = None

        self._source_cards: list[LocalSourceCard] = []
        self._folder_widgets: list[LocalFolderOptionWidget] = []
        self._folder_files_cache: dict[Path, list[MergedFile]] = {}  # Fast in-memory cache of folder files

        self._init_ui()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._load_sources()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(10)

        # Title
        title = QLabel("Criar Backup", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # Main Split Panel
        split_layout = QHBoxLayout()
        split_layout.setSpacing(12)

        # Left Pane (Sources)
        self._init_left_pane(split_layout)

        # Right Pane (Config & Folders selection)
        self._init_right_pane(split_layout)

        root.addLayout(split_layout, stretch=1)

        # Footer
        self._init_footer(root)

    def _init_left_pane(self, split: QHBoxLayout) -> None:
        left_frame = QFrame()
        left_frame.setObjectName("SurfaceCard")
        left_frame.setFixedWidth(220)  # Keep size completely static and stable
        left_frame.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px; background: #FFFFFF; }}"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        hdr = QLabel("FONTES LOCAIS", left_frame)
        hdr.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;"
        )
        left_layout.addWidget(hdr)

        scroll = QScrollArea(left_frame)
        scroll.setWidgetResizable(True)
        self._sources_container = QWidget()
        self._sources_layout = QVBoxLayout(self._sources_container)
        self._sources_layout.setAlignment(Qt.AlignTop)
        self._sources_layout.setSpacing(6)
        self._sources_layout.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self._sources_container)
        left_layout.addWidget(scroll)

        split.addWidget(left_frame)

    def _init_right_pane(self, split: QHBoxLayout) -> None:
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # Folder Card (stretching completely vertically)
        folder_card = QFrame()
        folder_card.setObjectName("SurfaceCard")
        folder_card.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px; background: #FFFFFF; }}"
        )
        folder_card_layout = QVBoxLayout(folder_card)
        folder_card_layout.setContentsMargins(0, 12, 0, 12)  # 0 left/right margin to match ConfirmView
        folder_card_layout.setSpacing(8)

        # Header layout containing "SELECIONAR PASTAS" title and "Pular mídias e executáveis" checkbox as a tag
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(16, 0, 16, 0)  # 16 left/right margin to keep header aligned

        self._folder_title = QLabel("SELECIONAR PASTAS", folder_card)
        self._folder_title.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;"
        )

        # Checkbox option layout styled as DefaultCheckbox
        chk_layout = QHBoxLayout()
        chk_layout.setContentsMargins(0, 0, 0, 0)
        chk_layout.setSpacing(6)

        self._chk_skip_media = QCheckBox(folder_card)
        self._chk_skip_media.setChecked(True)
        self._chk_skip_media.setObjectName("DefaultCheckbox")
        self._chk_skip_media.setFixedWidth(18)
        self._chk_skip_media.setCursor(Qt.PointingHandCursor)
        self._chk_skip_media.toggled.connect(self._trigger_recalculate)

        chk_lbl = QLabel("Pular mídias e executáveis", folder_card)
        chk_lbl.setStyleSheet("""
            font-size: 12px;
            font-weight: 400;
            color: #4A5568;
            background: transparent;
            border: none;
        """)
        chk_lbl.setCursor(Qt.PointingHandCursor)
        chk_lbl.mousePressEvent = lambda event: self._chk_skip_media.setChecked(not self._chk_skip_media.isChecked())

        chk_layout.addWidget(self._chk_skip_media)
        chk_layout.addWidget(chk_lbl)

        header_layout.addWidget(self._folder_title)
        header_layout.addStretch()
        header_layout.addLayout(chk_layout)
        folder_card_layout.addLayout(header_layout)

        # Scroll Area for grouped folders selection list (no outer border, matching ConfirmView)
        scroll = QScrollArea(folder_card)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        self._folders_container = QWidget()
        self._folders_container.setStyleSheet("background: transparent;")
        self._folders_layout = QVBoxLayout(self._folders_container)
        self._folders_layout.setAlignment(Qt.AlignTop)
        self._folders_layout.setSpacing(8)
        self._folders_layout.setContentsMargins(16, 0, 16, 0)  # 16 left/right padding to give spacing from scroll bar and borders
        scroll.setWidget(self._folders_container)
        folder_card_layout.addWidget(scroll, stretch=1)
        
        right_layout.addWidget(folder_card, stretch=1)

        # Wrap in right container widget and hide initially
        self._right_widget = right_container
        self._right_widget.setVisible(False)

        # Placeholder widget
        self._right_placeholder = QWidget()
        ph_lay = QVBoxLayout(self._right_placeholder)
        ph_lay.setAlignment(Qt.AlignCenter)
        ph_lbl = QLabel("Selecione uma ou mais fontes à esquerda\npara ver seus detalhes.", self._right_placeholder)
        ph_lbl.setAlignment(Qt.AlignCenter)
        ph_lbl.setWordWrap(True)
        ph_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        ph_lay.addWidget(ph_lbl)

        split.addWidget(self._right_placeholder, stretch=3)
        split.addWidget(self._right_widget, stretch=3)

    def _init_footer(self, root: QVBoxLayout) -> None:
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        # Voltar button
        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back_clicked)
        footer_layout.addWidget(self._back_btn)

        # Action Button (beside Voltar)
        self._start_btn = QPushButton("Continuar", self)
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_continue)
        self._start_btn.setEnabled(False)
        footer_layout.addWidget(self._start_btn)

        footer_layout.addStretch()

        # Estimates Bento boxes (on the right) - height restored to 48px
        self._size_card = BentoBox("TAMANHO ESTIMADO", "0 B", "Arquivos selecionados")
        self._time_card = BentoBox("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
        self._size_card.setFixedHeight(48)
        self._time_card.setFixedHeight(48)
        self._size_card.setFixedWidth(160)
        self._time_card.setFixedWidth(160)
        footer_layout.addWidget(self._size_card)
        footer_layout.addWidget(self._time_card)

        root.addLayout(footer_layout)

    def _on_back_clicked(self) -> None:
        self._stop_all_workers()
        self.back_requested.emit()

    def _stop_all_workers(self) -> None:
        """Stop all background thread tasks safely to prevent memory leak/crashes."""
        if self._discovery_worker is not None and self._discovery_worker.isRunning():
            self._discovery_worker.terminate()
            self._discovery_worker.wait()
            self._discovery_worker = None

        if self._detail_scanner_worker is not None and self._detail_scanner_worker.isRunning():
            self._detail_scanner_worker.terminate()
            self._detail_scanner_worker.wait()
            self._detail_scanner_worker = None

    def _load_sources(self) -> None:
        """Instantiate source cards immediately and scan their sizes/times in the background."""
        self._stop_all_workers()

        # Hide right details menu and show placeholder initially
        self._right_widget.setVisible(False)
        self._right_placeholder.setVisible(True)

        self._selected_files = []
        self._total_bytes = 0
        self._folder_files_cache = {}
        self._size_card.update_content("TAMANHO ESTIMADO", "0 B", "Arquivos selecionados")
        self._time_card.update_content("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
        self._start_btn.setEnabled(False)

        # Clear layouts
        while self._sources_layout.count():
            item = self._sources_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        while self._folders_layout.count():
            item = self._folders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._source_cards = []
        self._folder_widgets = []

        # Retrieve profile names and drive paths (near instant)
        profiles = get_local_user_profiles()
        drives = get_local_drives()
        if not drives:
            drives = get_drives_fallback()

        # Add "Discos Locais:" grouping header only if there is more than 1 confirmed drive
        if len(drives) > 1:
            lbl = QLabel("Discos Locais:")
            lbl.setStyleSheet(f"font-weight: bold; color: {RM_ACCENT}; font-size: 11px; margin-top: 8px; background: transparent; border: none;")
            self._sources_layout.addWidget(lbl)

        # Add drives first (always shown, including C:)
        for drive in sorted(drives):
            drive_str = str(drive)
            drive_name = f"Disco ({drive_str.rstrip(os.sep)})"
            card = LocalSourceCard("drive", drive_name, drive, PENDING_STATS, 0.0, False, self._sources_container)
            card.clicked.connect(self._on_source_card_clicked)
            self._sources_layout.addWidget(card)
            self._source_cards.append(card)

        # Order logged in user on top of other profiles
        active_profile = None
        other_profiles = []
        current_user = detect_user_login().strip()

        for profile in sorted(profiles):
            if profile.strip().lower() == current_user.lower():
                active_profile = profile
            else:
                other_profiles.append(profile)

        # Add active profile second (right under drives)
        if active_profile is not None:
            base_path = Path("C:\\Users") / active_profile
            card = LocalSourceCard("profile", active_profile, base_path, PENDING_STATS, 0.0, True, self._sources_container)
            card.clicked.connect(self._on_source_card_clicked)
            self._sources_layout.addWidget(card)
            self._source_cards.append(card)

        # Add other profiles last
        for profile in other_profiles:
            base_path = Path("C:\\Users") / profile
            card = LocalSourceCard("profile", profile, base_path, PENDING_STATS, 0.0, False, self._sources_container)
            card.clicked.connect(self._on_source_card_clicked)
            self._sources_layout.addWidget(card)
            self._source_cards.append(card)

        self._sources_layout.addStretch()

        # Gather sources list to scan details lazily
        sources_to_scan = []
        for card in self._source_cards:
            sources_to_scan.append((card.source_type, card.name, card.path))

        # Start the background stats scanner
        self._discovery_worker = LocalSourceDetailWorker(sources_to_scan)
        self._discovery_worker.stats_calculated.connect(self._on_stats_calculated)
        self._discovery_worker.start()

    def _on_stats_calculated(self, source_type: str, name: str, size_bytes: int, modified_time: float) -> None:
        """Update card stats lazily as calculation completes."""
        for card in self._source_cards:
            if card.source_type == source_type and card.name == name:
                card.update_stats(size_bytes, modified_time)
                break

    def _on_source_card_clicked(self, card: LocalSourceCard) -> None:
        """Toggle selection of the clicked card and update right side menu (multi-select)."""
        card.selected = not card.selected
        card.update_style()

        selected_cards = [c for c in self._source_cards if c.selected]

        if not selected_cards:
            self._right_widget.setVisible(False)
            self._right_placeholder.setVisible(True)
            
            # Clear folders layout
            while self._folders_layout.count():
                item = self._folders_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._folder_widgets = []
            self._folder_files_cache = {}
            self._trigger_recalculate()
        else:
            self._right_placeholder.setVisible(False)
            self._right_widget.setVisible(True)
            self._populate_folders_multi()

    def _populate_folders_multi(self) -> None:
        # Clear previous folders
        while self._folders_layout.count():
            item = self._folders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._folder_widgets = []
        self._folder_files_cache = {}

        selected_cards = [c for c in self._source_cards if c.selected]
        folders_to_scan = []

        for card in selected_cards:
            # Group container
            group_widget = QWidget()
            group_layout = QVBoxLayout(group_widget)
            group_layout.setContentsMargins(0, 4, 0, 4)
            group_layout.setSpacing(4)

            # Group header (uppercase)
            group_title = card.name.upper()
            header_lbl = QLabel(group_title, group_widget)
            header_lbl.setStyleSheet(
                f"font-size: 10px; font-weight: 800; color: {RM_TEXT_MUTED}; letter-spacing: 1px; background: transparent; border: none;"
            )
            group_layout.addWidget(header_lbl)

            has_any = False

            if card.source_type == "profile":
                for display_name, sub_paths in _PROFILE_SUBFOLDERS:
                    paths_list = [sub_paths] if isinstance(sub_paths, str) else sub_paths
                    existing_paths = []
                    for sub_rel in paths_list:
                        p = card.path / sub_rel
                        if p.exists():
                            existing_paths.append(p)
                    
                    if existing_paths:
                        has_any = True
                        widget_path = existing_paths[0] if len(existing_paths) == 1 else existing_paths
                        widget = LocalFolderOptionWidget(
                            display_name=display_name,
                            path=widget_path,
                            item_type="profile_folder",
                            profile=card.name,
                            parent=group_widget
                        )
                        widget.toggled.connect(self._trigger_recalculate)
                        group_layout.addWidget(widget)
                        self._folder_widgets.append(widget)
                        
                        for p in existing_paths:
                            folders_to_scan.append(("profile_folder", p, card.name))
            else:
                # Drive
                try:
                    for entry in sorted(card.path.iterdir(), key=lambda x: x.name.lower()):
                        if entry.is_dir() and entry.name.lower() not in _SYSTEM_ROOT_FOLDERS:
                            has_any = True
                            widget = LocalFolderOptionWidget(
                                display_name=entry.name,
                                path=entry,
                                item_type="drive_folder",
                                profile="RAIZ",
                                parent=group_widget
                            )
                            widget.toggled.connect(self._trigger_recalculate)
                            group_layout.addWidget(widget)
                            self._folder_widgets.append(widget)
                            folders_to_scan.append(("drive_folder", entry, "RAIZ"))
                except OSError:
                    pass

            if has_any:
                self._folders_layout.addWidget(group_widget)

        self._folders_layout.addStretch()

        if self._detail_scanner_worker is not None and self._detail_scanner_worker.isRunning():
            self._detail_scanner_worker.terminate()
            self._detail_scanner_worker.wait()

        if folders_to_scan:
            self._detail_scanner_worker = LocalSourceDetailScannerWorker(folders_to_scan)
            self._detail_scanner_worker.folder_scanned.connect(self._on_folder_scanned)
            self._detail_scanner_worker.finished.connect(self._trigger_recalculate)
            self._detail_scanner_worker.start()
        else:
            self._trigger_recalculate()

    def _on_folder_scanned(self, folder_path: Path, files: list[MergedFile]) -> None:
        """Update folder stats and cache them. Hide folders with zero files or custom conditions."""
        self._folder_files_cache[folder_path] = files
        self._trigger_recalculate()

    def _trigger_recalculate(self) -> None:
        """Recalculate selected files instantly using the in-memory cache."""
        from services.backup_creator import should_skip_file
        skip_media = self._chk_skip_media.isChecked()
        
        selected_files = []
        total_bytes = 0
        
        for widget in getattr(self, "_folder_widgets", []):
            paths_list = widget.path if isinstance(widget.path, list) else [widget.path]
            
            # Check if all subpaths are cached
            all_cached = True
            widget_files = []
            
            for p in paths_list:
                cached = self._folder_files_cache.get(p)
                if cached is None:
                    all_cached = False
                    break
                widget_files.extend(cached)
                
            if all_cached:
                filtered_files = []
                for f in widget_files:
                    if skip_media and should_skip_file(f.relative_name):
                        continue
                    filtered_files.append(f)
                
                widget_total_bytes = sum(f.size_bytes for f in filtered_files)
                widget_file_count = len(filtered_files)
                
                widget.set_stats(widget_file_count, widget_total_bytes)
                
                # Check exclusion conditions
                if widget.display_name == "Notas Autodesivas" and widget_total_bytes == 0:
                    widget.setVisible(False)
                    widget.checkbox.blockSignals(True)
                    widget.checkbox.setChecked(False)
                    widget.checkbox.blockSignals(False)
                    widget.selected = False
                elif widget_file_count == 0:
                    widget.setVisible(False)
                    widget.checkbox.blockSignals(True)
                    widget.checkbox.setChecked(False)
                    widget.checkbox.blockSignals(False)
                    widget.selected = False
                elif widget.checkbox.isChecked():
                    widget.setVisible(True)
                    widget.selected = True

                if widget.selected:
                    selected_files.extend(filtered_files)
                    total_bytes += widget_total_bytes

        self._selected_files = selected_files
        self._total_bytes = total_bytes
        
        self._size_card.update_content("TAMANHO ESTIMADO", _format_bytes(total_bytes), f"{len(selected_files)} arquivos")
        self._update_time_estimate()
        
        self._start_btn.setEnabled(len(selected_files) > 0)

    def _update_time_estimate(self) -> None:
        if not self._selected_files:
            self._time_card.update_content("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
            return
        est_seconds = estimate_copy_seconds_for_files(self._selected_files, self._write_speed)
        self._time_card.update_content("TEMPO DE OPERAÇÃO", _format_time(est_seconds), "Estimativa de cópia")

    def _on_continue(self) -> None:
        """Advance to next view passing selected files and exclusions option."""
        if not self._selected_files:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo selecionado para backup.")
            return
        self._stop_all_workers()
        self.continue_requested.emit(self._selected_files, self._chk_skip_media.isChecked())


class AdminCreateBackupConfigView(QWidget):
    """View to configure OS and Destination targets for local backup after folder selection."""
    back_requested = pyqtSignal()
    start_backup_requested = pyqtSignal(list, Path, bool)  # files, dest_root, skip_media_exec

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._files: list[MergedFile] = []
        self._skip_media_exec: bool = True
        self._write_speed: int = 50_000_000
        self._local_path_value: str = ""
        
        self._os_worker: Optional[CreateOSWorker] = None
        self._benchmark_worker: Optional[BenchmarkWorker] = None
        
        self._init_ui()

    def setup(self, files: list[MergedFile], skip_media_exec: bool) -> None:
        self._files = files
        self._skip_media_exec = skip_media_exec
        
        # Reset input states
        self._os_input.setText("")
        self._update_start_button_text()
        self._local_path_value = ""
        self._update_destination_display()
        
        # Update Bento boxes
        total_bytes = sum(f.size_bytes for f in files)
        self._size_card.update_content("TAMANHO ESTIMADO", _format_bytes(total_bytes), f"{len(files)} arquivos")
        self._update_time_estimate()
        
        self._validate_start_state()
        self._run_benchmark()

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(14)

        # Title
        title = QLabel("Configurar Backup", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # Center container taking up all remaining stretch space
        center_container = QWidget(self)
        center_layout = QVBoxLayout(center_container)
        center_layout.setContentsMargins(0, 30, 0, 0)  # Position Bento cards and options further down
        center_layout.setSpacing(10)  # Tight spacing between elements

        # 1. Estimates Bento boxes (placed on top, width 180px, height 72px)
        estimates_layout = QHBoxLayout()
        estimates_layout.setContentsMargins(0, 0, 0, 0)
        estimates_layout.setSpacing(12)
        estimates_layout.setAlignment(Qt.AlignCenter)

        self._size_card = BentoBox("TAMANHO ESTIMADO", "0 B", "Arquivos selecionados")
        self._time_card = BentoBox("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
        self._size_card.setFixedHeight(72)
        self._time_card.setFixedHeight(72)
        self._size_card.setFixedWidth(180)
        self._time_card.setFixedWidth(180)
        estimates_layout.addWidget(self._size_card)
        estimates_layout.addWidget(self._time_card)
        center_layout.addLayout(estimates_layout)
        
        # Add controlled margin spacing between bento cards and options
        center_layout.addSpacing(24)

        # 2. OS Input row (centered, free-standing, right below the cards)
        os_widget = QWidget(self)
        os_layout = QHBoxLayout(os_widget)
        os_layout.setContentsMargins(0, 0, 0, 0)
        os_layout.setSpacing(0)
        os_layout.setAlignment(Qt.AlignCenter)

        self._os_input = QLineEdit()
        self._os_input.setPlaceholderText("Ordem de Serviço (número)")
        self._os_input.setFixedWidth(240)
        self._os_input.setStyleSheet(
            "border: 1px solid #DDDDDD; border-radius: 6px; padding: 6px 10px; background: #FFFFFF;"
        )
        self._os_input.setValidator(QIntValidator(0, 999999, self))
        self._os_input.setMaxLength(6)
        self._os_input.textChanged.connect(self._update_start_button_text)
        self._os_input.textChanged.connect(self._on_os_text_changed)
        os_layout.addWidget(self._os_input)
        center_layout.addWidget(os_widget)

        # 3. Destination Toggle Row (centered, free-standing, below OS input)
        dest_widget = QWidget(self)
        dest_layout = QHBoxLayout(dest_widget)
        dest_layout.setContentsMargins(0, 0, 0, 0)
        dest_layout.setSpacing(12)
        dest_layout.setAlignment(Qt.AlignCenter)

        dest_lbl = QLabel("Destino:")
        dest_lbl.setStyleSheet("font-weight: bold; background: transparent; border: none;")
        self._dest_group = QButtonGroup(self)
        self._r_network = QRadioButton("Rede")
        self._r_network.setChecked(True)
        self._r_local = QRadioButton("Local")
        self._r_network.setStyleSheet("background: transparent; border: none;")
        self._r_local.setStyleSheet("background: transparent; border: none;")
        self._dest_group.addButton(self._r_network)
        self._dest_group.addButton(self._r_local)
        self._r_network.toggled.connect(self._on_dest_type_changed)

        dest_layout.addWidget(dest_lbl)
        dest_layout.addWidget(self._r_network)
        dest_layout.addWidget(self._r_local)
        center_layout.addWidget(dest_widget)

        # 4. Destination Path Button (styled with inner Modificar tag layout)
        self._local_path_widget = QWidget()
        self._local_path_widget.setStyleSheet("background: transparent; border: none;")
        local_path_layout = QHBoxLayout(self._local_path_widget)
        local_path_layout.setContentsMargins(0, 0, 0, 0)
        local_path_layout.setAlignment(Qt.AlignCenter)

        self._local_path_btn = QPushButton(self)
        self._local_path_btn.setCursor(Qt.PointingHandCursor)
        self._local_path_btn.setFixedWidth(340)
        self._local_path_btn.clicked.connect(self._on_browse_local_path)
        
        # Inner layout inside path button to contain text + Modificar tag
        self._path_btn_layout = QHBoxLayout(self._local_path_btn)
        self._path_btn_layout.setContentsMargins(12, 0, 12, 0)
        self._path_btn_layout.setSpacing(8)

        self._path_text_lbl = QLabel("Selecione a pasta de destino...", self._local_path_btn)
        self._path_text_lbl.setAlignment(Qt.AlignCenter)
        self._path_text_lbl.setStyleSheet("color: #4A5568; font-size: 12px; background: transparent; border: none;")
        self._path_btn_layout.addWidget(self._path_text_lbl, 1)

        self._modificar_tag_lbl = QLabel("Modificar", self._local_path_btn)
        self._modificar_tag_lbl.setAlignment(Qt.AlignCenter)
        self._modificar_tag_lbl.setFixedSize(64, 20)
        self._modificar_tag_lbl.setStyleSheet("""
            QLabel {
                border: 1px solid #3B6EA5;
                border-radius: 4px;
                background-color: #EBF3FC;
                color: #3B6EA5;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        self._path_btn_layout.addWidget(self._modificar_tag_lbl)
        self._modificar_tag_lbl.setVisible(False)

        local_path_layout.addWidget(self._local_path_btn)
        center_layout.addWidget(self._local_path_widget)

        # 5. Add stretch at bottom to push options upward right below Bento cards
        center_layout.addStretch(1)

        root.addWidget(center_container, stretch=1)

        # 6. Buttons Row (Voltar, Começar Backup) placed at the bottom, centered side-by-side matching AnalysisView
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self._on_back_clicked)

        self._start_btn = QPushButton("Criar OS e começar backup", self)
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start_backup)
        self._start_btn.setEnabled(False)

        btn_row.addStretch()
        btn_row.addWidget(self._back_btn)
        btn_row.addWidget(self._start_btn)
        btn_row.addStretch()

        root.addLayout(btn_row)

    def _update_start_button_text(self) -> None:
        os_num = self._os_input.text().strip()
        if not os_num:
            self._start_btn.setText("Criar OS e começar backup")
        else:
            self._start_btn.setText("Começar Backup")

    def _on_os_text_changed(self) -> None:
        self._update_destination_display()

    def _format_display_path(self, path: str, max_chars: int = 40) -> str:
        """Elide long directory paths dynamically to fit inside the button container."""
        if len(path) <= max_chars:
            return path

        # For network paths (UNC): keep server IP e.g. \\192.168.11.245\...
        if path.startswith("\\\\"):
            normalized = path.replace("/", "\\")
            parts = [p for p in normalized.split("\\") if p]
            if len(parts) >= 2:
                server = parts[0]
                last_part = parts[-1]
                elided = f"\\\\{server}\\...\\{last_part}"
                if len(elided) <= max_chars:
                    return elided

        # For local absolute paths: keep drive letter e.g. C:\...\Folder
        if len(path) > 3 and path[1:3] == ":\\":
            drive = path[0:3]
            normalized = path.replace("/", "\\")
            last_part = normalized.split("\\")[-1]
            elided = f"{drive}...\\{last_part}"
            if len(elided) <= max_chars:
                return elided

        # Slicing fallback
        return "..." + path[-(max_chars - 3):]

    def _update_destination_display(self) -> None:
        """Update path display button style and validate enable states based on selection type."""
        is_network = self._r_network.isChecked()
        if is_network:
            dest_path = self._resolve_backup_destination_root()
            self._path_text_lbl.setText(self._format_display_path(str(dest_path), max_chars=50))
            self._path_text_lbl.setAlignment(Qt.AlignCenter)
            self._local_path_btn.setEnabled(False)
            self._local_path_btn.setFixedWidth(340)
            self._modificar_tag_lbl.setVisible(False)
            self._local_path_btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #E2E8F0;
                    border-radius: 6px;
                    padding: 6px 12px;
                    background-color: #EDF2F7;
                    color: #718096;
                    font-size: 11px;
                }
            """)
            self._path_text_lbl.setStyleSheet("color: #718096; font-size: 11px; background: transparent; border: none;")
        else:
            self._local_path_btn.setEnabled(True)
            self._local_path_btn.setFixedWidth(340)
            self._local_path_btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #CBD5E0;
                    border-radius: 6px;
                    padding: 6px 12px;
                    background-color: #FFFFFF;
                    color: #4A5568;
                    font-size: 12px;
                }
                QPushButton:hover {
                    border-color: #A0AEC0;
                    background-color: #F7FAFC;
                }
            """)
            self._path_text_lbl.setAlignment(Qt.AlignCenter)
            self._path_text_lbl.setStyleSheet("color: #4A5568; font-size: 12px; background: transparent; border: none;")
            if self._local_path_value:
                self._path_text_lbl.setText(self._format_display_path(self._local_path_value, max_chars=36))
                self._modificar_tag_lbl.setVisible(True)
            else:
                self._path_text_lbl.setText("Selecione a pasta de destino...")
                self._modificar_tag_lbl.setVisible(False)

        self._validate_start_state()

    def _validate_start_state(self) -> None:
        """Check if backup meets conditions to start (checking if local path is selected if destination is Local)."""
        has_files = len(self._files) > 0
        dest_valid = True
        if self._r_local.isChecked():
            dest_valid = bool(self._local_path_value.strip())
        self._start_btn.setEnabled(has_files and dest_valid)

    def _on_back_clicked(self) -> None:
        self._stop_workers()
        self.back_requested.emit()

    def _stop_workers(self) -> None:
        if self._os_worker is not None and self._os_worker.isRunning():
            self._os_worker.terminate()
            self._os_worker.wait()
            self._os_worker = None
        if self._benchmark_worker is not None and self._benchmark_worker.isRunning():
            self._benchmark_worker.terminate()
            self._benchmark_worker.wait()
            self._benchmark_worker = None

    def _on_dest_type_changed(self) -> None:
        self._update_destination_display()
        self._run_benchmark()

    def _on_browse_local_path(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Destino")
        if dir_path:
            self._local_path_value = dir_path
            self._update_destination_display()
            self._run_benchmark()

    def _generate_os_and_start_backup(self) -> None:
        import socket
        hostname = socket.gethostname()
        from services.backup_discovery import detect_user_login
        user_login = detect_user_login()

        self._start_btn.setEnabled(False)
        self._start_btn.setText("Gerando OS...")
        self._back_btn.setEnabled(False)

        self._os_worker = CreateOSWorker(hostname, user_login)
        self._os_worker.finished.connect(self._on_os_generated_for_start)
        self._os_worker.start()

    def _on_os_generated_for_start(self, ticket_id: int) -> None:
        self._back_btn.setEnabled(True)
        self._start_btn.setEnabled(True)
        self._update_start_button_text()

        if ticket_id > 0:
            self._os_input.setText(str(ticket_id))
            dest_root = self._resolve_backup_destination_root()
            if dest_root is not None:
                self._proceed_to_start_backup(dest_root)
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível gerar a OS automaticamente. Por favor, insira o número manualmente.")

    def _run_benchmark(self) -> None:
        import sys
        if "unittest" in sys.modules or "pytest" in sys.modules:
            return

        target_dir = self._resolve_backup_destination_root()
        if not target_dir:
            return

        if self._benchmark_worker is not None and self._benchmark_worker.isRunning():
            return

        self._benchmark_worker = BenchmarkWorker(target_dir)
        self._benchmark_worker.finished.connect(self._on_benchmark_finished)
        self._benchmark_worker.start()

    def _on_benchmark_finished(self, local_speed: float, network_speed: float) -> None:
        self._write_speed = int(local_speed) if local_speed > 0 else 50_000_000
        self._update_time_estimate()

    def _update_time_estimate(self) -> None:
        if not self._files:
            self._time_card.update_content("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
            return
        est_seconds = estimate_copy_seconds_for_files(self._files, self._write_speed)
        self._time_card.update_content("TEMPO DE OPERAÇÃO", _format_time(est_seconds), "Estimativa de cópia")

    def _resolve_backup_destination_root(self) -> Optional[Path]:
        import socket
        hostname = socket.gethostname()
        os_num = self._os_input.text().strip() or "0"
        folder_name = f"OS_{os_num}_{hostname}"

        if self._r_network.isChecked():
            cfg = get_server_config()
            server = cfg.server_ip or "192.168.11.245"
            share = cfg.backup_share or "backups"
            return Path(f"\\\\{server}\\{share}") / folder_name
        else:
            local_target = self._local_path_value.strip()
            if not local_target:
                return None
            return Path(local_target) / folder_name

    def _on_start_backup(self) -> None:
        # Validate Target path
        dest_root = self._resolve_backup_destination_root()
        if dest_root is None:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione a pasta local de destino.")
            return

        # Validate selections
        if not self._files:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo selecionado para backup.")
            return

        os_num = self._os_input.text().strip()
        if not os_num:
            self._generate_os_and_start_backup()
        else:
            self._proceed_to_start_backup(dest_root)

    def _proceed_to_start_backup(self, dest_root: Path) -> None:
        if self._r_network.isChecked():
            parent = dest_root.parent
            if not parent.exists():
                QMessageBox.critical(
                    self, "Erro",
                    f"Compartilhamento de rede inacessível:\n{parent}\n"
                    "Verifique a conexão ou as credenciais de rede."
                )
                return

        self._stop_workers()
        self.start_backup_requested.emit(self._files, dest_root, self._skip_media_exec)
