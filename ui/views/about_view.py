from __future__ import annotations

import os
import sys
import socket
import platform
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame

from config import get_app_name, get_server_config, get_api_config, is_test_mode
from services.backup_discovery import detect_user_login, extract_machine_id


class AboutView(QWidget):
    """AboutView — displays credits and system debug info.

    Example:
        view = AboutView()
        view.back_requested.connect(on_back)
    """

    back_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None) -> None:
        """Initialize the About view.

        Example:
            view = AboutView()
        """
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        """Build layout with diagnostic cards and a back button.

        Example:
            self._init_ui()
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self._create_header(layout)
        layout.addWidget(self._create_info_card())
        layout.addStretch()

        self._back_btn = self._create_back_button()
        layout.addWidget(self._back_btn, alignment=Qt.AlignCenter)

    def _create_header(self, layout: QVBoxLayout) -> None:
        """Create and add header labels to the layout.

        Example:
            self._create_header(layout)
        """
        title = QLabel(f"Sobre o {get_app_name()}", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Solucionado por Tiago Vieira e Jean S.\nDesenvolvido na Secretaria de Tecnologia e Inovação de Caraguatatuba/SP.\n\n2026 © Todos os direitos reservados.", self)
        subtitle.setObjectName("ViewSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

    def _get_diagnostic_info(self) -> list[str]:
        """Collect diagnostic details about the app and system.

        Example:
            lines = self._get_diagnostic_info()
        """
        login = detect_user_login()
        hostname = socket.gethostname()
        mid = extract_machine_id(hostname) or "não identificada"
        server_cfg = get_server_config()
        api_cfg = get_api_config()
        py_ver = sys.version.split()[0]
        return [
            f"Versão: {api_cfg.app_version}",
            f"Usuário logado: {login}",
            f"Identificação da máquina: {hostname} ({mid})",
            f"Servidor de backups: {server_cfg.server_ip} (share: {server_cfg.backup_share})",
            f"Modo de teste: {'Ativo' if is_test_mode() else 'Inativo'}"
        ]

    def _create_info_card(self) -> QFrame:
        """Create card widget filled with diagnostic info.

        Example:
            card = self._create_info_card()
        """
        card = QFrame(self)
        card.setObjectName("BentoCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(6)
        for line in self._get_diagnostic_info():
            lbl = QLabel(line, card)
            lbl.setObjectName("BentoSub")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background: transparent;")
            card_layout.addWidget(lbl)
        return card

    def _create_back_button(self) -> QPushButton:
        """Create and configure the back button.

        Example:
            btn = self._create_back_button()
        """
        btn = QPushButton("Voltar", self)
        btn.setObjectName("SecondaryButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(120)
        btn.clicked.connect(self.back_requested.emit)
        return btn
