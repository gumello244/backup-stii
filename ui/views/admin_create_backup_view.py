from __future__ import annotations

"""AdminCreateBackupView — configure and execute local backups.

Allows the admin to select sources (profiles, drives) on the left pane, and configure
the backup target, OS number (automatically via PORTUS or manually), exclusions,
and select folders to back up on the right pane. Shows live size and time estimates.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QRadioButton, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QButtonGroup, QGroupBox
)

from ui.assets import RM_BORDER, RM_TEXT_MUTED, RM_SURFACE, RM_ACCENT
from ui.components import BentoBox
from ui.format_utils import format_bytes as _format_bytes, format_time as _format_time
from services.admin_backup_discovery import get_local_user_profiles, get_local_drives
from services.backup_discovery import get_local_drives as get_drives_fallback
from services.backup_merger import MergedFile
from services.copy_benchmark import run_write_benchmark, estimate_copy_seconds_for_files
from ui.workers import CreateOSWorker, BenchmarkWorker

logger = logging.getLogger(__name__)

# Standard user folders mapped for backup
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
    ("Sticky Notes (Antigo)", "AppData/Roaming/Microsoft/Sticky Notes"),
    ("Sticky Notes (Novo)", "AppData/Local/Packages/Microsoft.MicrosoftStickyNotes_8wekyb3d8bbwe"),
    ("Outlook Local", "AppData/Local/Microsoft/Outlook"),
    ("Outlook Assinaturas", "AppData/Roaming/Microsoft/Assinaturas"),
    ("Outlook Roaming", "AppData/Roaming/Microsoft/Outlook"),
]

# Root system folders to exclude under C:\
_SYSTEM_ROOT_FOLDERS = {
    "arquivos de programas", "arquivos de programas (x86)", "program files",
    "program files (x86)", "inetpub", "intel", "dell", "msocache", "perflogs",
    "programdata", "temp", "users", "windows", "recovery", "system volume information",
    "$recycle.bin", "config.msi", "documents and settings", "$winreagent", "boot",
    "efi", "pagefile.sys", "swapfile.sys", "hiberfil.sys", "dumpstack.log"
}


class LocalFolderScannerWorker(QThread):
    """Background worker to scan checked folders and compile files/sizes without freezing the UI."""
    finished = pyqtSignal(list, int)  # list[MergedFile], total_bytes

    def __init__(self, selections: list[tuple[str, Path, str]], skip_media_exec: bool) -> None:
        super().__init__()
        self._selections = selections
        self._skip_media_exec = skip_media_exec

    def run(self) -> None:
        try:
            from services.backup_creator import should_skip_file
            files = []
            total_bytes = 0

            for item_type, folder_path, group_name in self._selections:
                if not folder_path.exists():
                    continue

                if folder_path.is_file():
                    # Singular file bookmark/settings
                    try:
                        st = folder_path.stat()
                        sz = st.st_size
                    except OSError:
                        continue
                    # Compute relative name
                    # e.g. AppData/Local/Google/Chrome/User Data/Default/Bookmarks
                    rel_name = folder_path.name
                    # Find matching relative path prefix from profile
                    for display, sub_rel in _PROFILE_SUBFOLDERS:
                        if folder_path.as_posix().endswith(sub_rel):
                            rel_name = sub_rel
                            break

                    files.append(MergedFile(
                        source_path=folder_path,
                        dest_folder=Path(rel_name).parent.as_posix() if "/" in rel_name else "AppData",
                        relative_name=Path(rel_name).name,
                        size_bytes=sz,
                        mtime=st.st_mtime,
                        target_profile=group_name if item_type == 'profile_folder' else None,
                    ))
                    total_bytes += sz
                    continue

                # Recursively walk directory
                for root, _, filenames in os.walk(folder_path):
                    for filename in filenames:
                        if filename.lower() in ("desktop.ini", "thumbs.db", ".ds_store"):
                            continue

                        if self._skip_media_exec and should_skip_file(filename):
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
                            # Profile folder: e.g. Desktop, Documents
                            dest_folder = folder_path.name
                            target_profile = group_name
                        else:
                            # Drive folder: e.g. C:\Dados -> RAIZ\Dados\...
                            dest_folder = "RAIZ"
                            parent_folder_name = folder_path.name
                            rel_name = f"{parent_folder_name}/{rel_name}"
                            target_profile = None

                        files.append(MergedFile(
                            source_path=file_path,
                            dest_folder=dest_folder,
                            relative_name=rel_name,
                            size_bytes=sz,
                            mtime=st.st_mtime,
                            target_profile=target_profile,
                        ))
                        total_bytes += sz

            self.finished.emit(files, total_bytes)
        except Exception as e:
            logger.error('{"event":"local_scanner_failed","error":"%s"}', e)
            self.finished.emit([], 0)


class AdminCreateBackupView(QWidget):
    """View to select local folders, generate OS, configure target, and trigger backup."""

    back_requested = pyqtSignal()
    start_backup_requested = pyqtSignal(list, Path, bool)  # list[MergedFile], dest_root, skip_media_exec

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._selected_files: list[MergedFile] = []
        self._total_bytes: int = 0
        self._write_speed: int = 50_000_000  # Default 50MB/s
        self._benchmark_worker: Optional[BenchmarkWorker] = None
        self._scanner_worker: Optional[LocalFolderScannerWorker] = None
        self._os_worker: Optional[CreateOSWorker] = None

        self._init_ui()
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
        left_frame.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px; background: #FFFFFF; }}"
        )
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        hdr = QLabel("FONTES LOCAIS", left_frame)
        hdr.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED}; letter-spacing: 1px; background: transparent;"
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

        split.addWidget(left_frame, stretch=2)

    def _init_right_pane(self, split: QHBoxLayout) -> None:
        right_frame = QFrame()
        right_frame.setObjectName("SurfaceCard")
        right_frame.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px; background: #FFFFFF; }}"
        )
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(10)

        # 1. OS & Target settings Group
        settings_layout = QVBoxLayout()
        settings_layout.setSpacing(6)

        # OS Row
        os_layout = QHBoxLayout()
        os_lbl = QLabel("OS:")
        os_lbl.setStyleSheet("font-weight: bold; min-width: 30px;")
        self._os_input = QLineEdit()
        self._os_input.setPlaceholderText("Ordem de Serviço (número)")
        self._os_input.setStyleSheet(
            "border: 1px solid #DDDDDD; border-radius: 6px; padding: 4px 8px; background: #FFFFFF;"
        )
        self._gen_os_btn = QPushButton("Gerar OS")
        self._gen_os_btn.setObjectName("SecondaryButton")
        self._gen_os_btn.setCursor(Qt.PointingHandCursor)
        self._gen_os_btn.clicked.connect(self._on_generate_os)
        os_layout.addWidget(os_lbl)
        os_layout.addWidget(self._os_input)
        os_layout.addWidget(self._gen_os_btn)
        settings_layout.addLayout(os_layout)

        # Destination Toggle Row
        dest_layout = QHBoxLayout()
        dest_lbl = QLabel("Destino:")
        dest_lbl.setStyleSheet("font-weight: bold; min-width: 60px;")
        self._dest_group = QButtonGroup(self)
        self._r_network = QRadioButton("Rede")
        self._r_network.setChecked(True)
        self._r_local = QRadioButton("Local")
        self._dest_group.addButton(self._r_network)
        self._dest_group.addButton(self._r_local)
        self._r_network.toggled.connect(self._on_dest_type_changed)
        dest_layout.addWidget(dest_lbl)
        dest_layout.addWidget(self._r_network)
        dest_layout.addWidget(self._r_local)
        dest_layout.addStretch()
        settings_layout.addLayout(dest_layout)

        # Local Path Selector Row (hidden by default)
        self._local_path_widget = QWidget()
        local_path_layout = QHBoxLayout(self._local_path_widget)
        local_path_layout.setContentsMargins(0, 0, 0, 0)
        local_path_layout.setSpacing(6)
        self._local_path_input = QLineEdit()
        self._local_path_input.setReadOnly(True)
        self._local_path_input.setPlaceholderText("Selecione a pasta de destino...")
        self._local_path_input.setStyleSheet(
            "border: 1px solid #DDDDDD; border-radius: 6px; padding: 4px 8px; background: #EEEEEE;"
        )
        self._browse_btn = QPushButton("...")
        self._browse_btn.setObjectName("SecondaryButton")
        self._browse_btn.setCursor(Qt.PointingHandCursor)
        self._browse_btn.clicked.connect(self._on_browse_local_path)
        local_path_layout.addWidget(self._local_path_input)
        local_path_layout.addWidget(self._browse_btn)
        self._local_path_widget.setVisible(False)
        settings_layout.addWidget(self._local_path_widget)

        # Exclusions Row
        self._chk_skip_media = QCheckBox("Pular mídias e executáveis (.mp3, .mp4, .exe, etc)")
        self._chk_skip_media.setChecked(True)
        self._chk_skip_media.toggled.connect(self._trigger_recalculate)
        settings_layout.addWidget(self._chk_skip_media)

        right_layout.addLayout(settings_layout)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {RM_BORDER};")
        right_layout.addWidget(sep)

        # 2. Checkable Folder tree
        scroll = QScrollArea(right_frame)
        scroll.setWidgetResizable(True)
        self._folders_container = QWidget()
        self._folders_layout = QVBoxLayout(self._folders_container)
        self._folders_layout.setAlignment(Qt.AlignTop)
        self._folders_layout.setSpacing(8)
        self._folders_layout.setContentsMargins(2, 2, 2, 2)
        scroll.setWidget(self._folders_container)
        right_layout.addWidget(scroll, stretch=1)

        split.addWidget(right_frame, stretch=3)

    def _init_footer(self, root: QVBoxLayout) -> None:
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(10)

        # Voltar button
        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)
        footer_layout.addWidget(self._back_btn)

        # Estimates Bento boxes
        self._size_card = BentoBox("TAMANHO ESTIMADO", "0 B", "Arquivos selecionados")
        self._time_card = BentoBox("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
        self._size_card.setFixedHeight(48)
        self._time_card.setFixedHeight(48)
        self._size_card.setFixedWidth(160)
        self._time_card.setFixedWidth(160)
        footer_layout.addStretch()
        footer_layout.addWidget(self._size_card)
        footer_layout.addWidget(self._time_card)

        # Action Button
        self._start_btn = QPushButton("Começar Backup", self)
        self._start_btn.setObjectName("PrimaryButton")
        self._start_btn.setCursor(Qt.PointingHandCursor)
        self._start_btn.clicked.connect(self._on_start_backup)
        self._start_btn.setEnabled(False)
        footer_layout.addWidget(self._start_btn)

        root.addLayout(footer_layout)

    # ------------------------------------------------------------------
    # Data Loading & Event Handlers
    # ------------------------------------------------------------------

    def _load_sources(self) -> None:
        """Scan local profiles and drives and build left pane checkboxes."""
        profiles = get_local_user_profiles()
        drives = get_local_drives()
        if not drives:
            drives = get_drives_fallback()

        self._profile_checks = {}
        self._drive_checks = {}

        # Clear layouts
        while self._sources_layout.count():
            item = self._sources_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Add profiles
        if profiles:
            lbl = QLabel("Perfis de Usuários:")
            lbl.setStyleSheet(f"font-weight: bold; color: {RM_ACCENT}; font-size: 11px; margin-top: 4px;")
            self._sources_layout.addWidget(lbl)
            for profile in sorted(profiles):
                chk = QCheckBox(profile)
                chk.setObjectName("DefaultCheckbox")
                chk.setCursor(Qt.PointingHandCursor)
                chk.toggled.connect(self._on_source_toggled)
                self._sources_layout.addWidget(chk)
                self._profile_checks[profile] = chk

        # Add drives
        if drives:
            lbl = QLabel("Discos Locais:")
            lbl.setStyleSheet(f"font-weight: bold; color: {RM_ACCENT}; font-size: 11px; margin-top: 8px;")
            self._sources_layout.addWidget(lbl)
            for drive in sorted(drives):
                drive_str = str(drive)
                chk = QCheckBox(f"Disco ({drive_str.rstrip(os.sep)})")
                chk.setObjectName("DefaultCheckbox")
                chk.setCursor(Qt.PointingHandCursor)
                chk.setProperty("drive_path", drive_str)
                chk.toggled.connect(self._on_source_toggled)
                self._sources_layout.addWidget(chk)
                self._drive_checks[drive_str] = chk

        self._sources_layout.addStretch()

    def _on_source_toggled(self) -> None:
        """Rebuild the folder checklist on the right pane based on checked sources."""
        # Clear right checklist layout
        while self._folders_layout.count():
            item = self._folders_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._folder_checkboxes = []

        # Add checked profiles
        for profile, chk in self._profile_checks.items():
            if chk.isChecked():
                group = QGroupBox(f"Usuário: {profile}")
                group.setStyleSheet("font-weight: bold; color: #1A202C;")
                glay = QVBoxLayout(group)
                glay.setSpacing(4)
                glay.setContentsMargins(8, 8, 8, 8)

                # Add profile subfolders that exist on disk
                base_path = Path("C:\\Users") / profile
                has_any = False
                for display_name, sub_rel in _PROFILE_SUBFOLDERS:
                    p = base_path / sub_rel
                    if p.exists():
                        has_any = True
                        folder_chk = QCheckBox(display_name)
                        folder_chk.setProperty("item_type", "profile_folder")
                        folder_chk.setProperty("path", str(p))
                        folder_chk.setProperty("profile", profile)
                        folder_chk.setChecked(True)
                        folder_chk.toggled.connect(self._trigger_recalculate)
                        glay.addWidget(folder_chk)
                        self._folder_checkboxes.append(folder_chk)

                if not has_any:
                    lbl = QLabel("Nenhuma pasta mapeada encontrada.")
                    lbl.setStyleSheet("color: #718096; font-weight: normal; font-size: 12px;")
                    glay.addWidget(lbl)

                self._folders_layout.addWidget(group)

        # Add checked drives
        for drive_str, chk in self._drive_checks.items():
            if chk.isChecked():
                drive_path = Path(drive_str)
                group = QGroupBox(f"Disco: {drive_str.rstrip(os.sep)}")
                group.setStyleSheet("font-weight: bold; color: #1A202C;")
                glay = QVBoxLayout(group)
                glay.setSpacing(4)
                glay.setContentsMargins(8, 8, 8, 8)

                # List non-system folders
                has_any = False
                try:
                    for entry in sorted(drive_path.iterdir(), key=lambda x: x.name.lower()):
                        if entry.is_dir() and entry.name.lower() not in _SYSTEM_ROOT_FOLDERS:
                            has_any = True
                            folder_chk = QCheckBox(entry.name)
                            folder_chk.setProperty("item_type", "drive_folder")
                            folder_chk.setProperty("path", str(entry))
                            folder_chk.setProperty("profile", "RAIZ")
                            folder_chk.setChecked(True)
                            folder_chk.toggled.connect(self._trigger_recalculate)
                            glay.addWidget(folder_chk)
                            self._folder_checkboxes.append(folder_chk)
                except OSError:
                    pass

                if not has_any:
                    lbl = QLabel("Nenhuma pasta incomum encontrada na raíz.")
                    lbl.setStyleSheet("color: #718096; font-weight: normal; font-size: 12px;")
                    glay.addWidget(lbl)

                self._folders_layout.addWidget(group)

        self._folders_layout.addStretch()

        # Recalculate sizes
        self._trigger_recalculate()
        # Refresh benchmark on source change/setup
        self._run_benchmark()

    def _on_dest_type_changed(self) -> None:
        """Show/hide directory chooser path if Local vs Network destination is toggled."""
        is_local = self._r_local.isChecked()
        self._local_path_widget.setVisible(is_local)
        self._run_benchmark()

    def _on_browse_local_path(self) -> None:
        """Open directories browser dialog to select local backup target."""
        dir_path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta de Destino")
        if dir_path:
            self._local_path_input.setText(dir_path)
            self._run_benchmark()

    def _on_generate_os(self) -> None:
        """Call PORTUS CREATE_OS event in background to auto-generate GLPI OS ticket."""
        # Find hostname
        import socket
        hostname = socket.gethostname()
        from services.backup_discovery import detect_user_login
        user_login = detect_user_login()

        self._gen_os_btn.setEnabled(False)
        self._gen_os_btn.setText("Gerando...")

        self._os_worker = CreateOSWorker(hostname, user_login)
        self._os_worker.finished.connect(self._on_os_generated)
        self._os_worker.start()

    def _on_os_generated(self, ticket_id: int) -> None:
        self._gen_os_btn.setEnabled(True)
        self._gen_os_btn.setText("Gerar OS")
        if ticket_id > 0:
            self._os_input.setText(str(ticket_id))
            QMessageBox.information(self, "OS Gerada", f"Ordem de Serviço #{ticket_id} criada com sucesso via PORTUS.")
        else:
            QMessageBox.warning(self, "Erro", "Não foi possível gerar a OS automaticamente. Por favor, insira o número manualmente.")

    def _run_benchmark(self) -> None:
        """Perform destination speed benchmark in background."""
        target_dir = self._resolve_backup_destination_root()
        if not target_dir:
            return

        if self._benchmark_worker is not None and self._benchmark_worker.isRunning():
            return

        self._benchmark_worker = BenchmarkWorker(target_dir)
        self._benchmark_worker.finished.connect(self._on_benchmark_finished)
        self._benchmark_worker.start()

    def _on_benchmark_finished(self, local_speed: float, network_speed: float) -> None:
        # Use whichever speed is non-zero (BenchmarkWorker writes to local_speed for the passed target path)
        self._write_speed = int(local_speed) if local_speed > 0 else 50_000_000
        self._update_time_estimate()

    def _trigger_recalculate(self) -> None:
        """Gather checked items and start background scanning of files and sizes."""
        if self._scanner_worker is not None and self._scanner_worker.isRunning():
            self._scanner_worker.terminate()
            self._scanner_worker.wait()

        selections = []
        for chk in getattr(self, "_folder_checkboxes", []):
            if chk.isChecked():
                item_type = chk.property("item_type")
                path = Path(chk.property("path"))
                profile = chk.property("profile")
                selections.append((item_type, path, profile))

        if not selections:
            self._selected_files = []
            self._total_bytes = 0
            self._size_card.update_content("TAMANHO ESTIMADO", "0 B", "Arquivos selecionados")
            self._time_card.update_content("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
            self._start_btn.setEnabled(False)
            return

        self._start_btn.setEnabled(False)
        self._start_btn.setText("Calculando...")

        self._scanner_worker = LocalFolderScannerWorker(selections, self._chk_skip_media.isChecked())
        self._scanner_worker.finished.connect(self._on_scan_finished)
        self._scanner_worker.start()

    def _on_scan_finished(self, files: list[MergedFile], total_bytes: int) -> None:
        self._selected_files = files
        self._total_bytes = total_bytes

        self._size_card.update_content("TAMANHO ESTIMADO", _format_bytes(total_bytes), f"{len(files)} arquivos")
        self._update_time_estimate()

        self._start_btn.setEnabled(len(files) > 0)
        self._start_btn.setText("Começar Backup")

    def _update_time_estimate(self) -> None:
        if not self._selected_files:
            self._time_card.update_content("TEMPO DE OPERAÇÃO", "0s", "Estimativa de cópia")
            return
        est_seconds = estimate_copy_seconds_for_files(self._selected_files, self._write_speed)
        self._time_card.update_content("TEMPO DE OPERAÇÃO", _format_time(est_seconds), "Estimativa de cópia")

    def _resolve_backup_destination_root(self) -> Optional[Path]:
        """Resolve destination path (network share or selected local directory)."""
        import socket
        hostname = socket.gethostname()
        os_num = self._os_input.text().strip() or "0"

        folder_name = f"OS_{os_num}_{hostname}"

        if self._r_network.isChecked():
            # Network share
            cfg = get_server_config()
            # If server_ip/backup_share not set, fallback to default or path
            server = cfg.server_ip or "192.168.11.245"
            share = cfg.backup_share or "Backups"
            return Path(f"\\\\{server}\\{share}") / folder_name
        else:
            local_target = self._local_path_input.text().strip()
            if not local_target:
                return None
            return Path(local_target) / folder_name

    def _on_start_backup(self) -> None:
        """Validate settings and trigger the backup requested signal."""
        # 1. Validate OS
        os_num = self._os_input.text().strip()
        if not os_num:
            QMessageBox.warning(self, "Aviso", "Por favor, insira ou gere o número da OS antes de prosseguir.")
            return

        # 2. Validate Target path
        dest_root = self._resolve_backup_destination_root()
        if dest_root is None:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione a pasta local de destino.")
            return

        # 3. Validate selections
        if not self._selected_files:
            QMessageBox.warning(self, "Aviso", "Nenhum arquivo selecionado para backup.")
            return

        # Double check network share parent directory writable/accessible if network selected
        if self._r_network.isChecked():
            # Validate share parent exists/writable
            parent = dest_root.parent
            if not parent.exists():
                QMessageBox.critical(
                    self, "Erro",
                    f"Compartilhamento de rede inacessível:\n{parent}\n"
                    "Verifique a conexão ou as credenciais de rede."
                )
                return

        self.start_backup_requested.emit(self._selected_files, dest_root, self._chk_skip_media.isChecked())
