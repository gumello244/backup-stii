from __future__ import annotations

"""Tela 4 — Progressão.

Apresenta uma barra de progresso proporcional a bytes, o nome do arquivo atual,
a porcentagem concluída e o tempo estimado restante (ETA). Também inclui um
BentoSpinner durante o estado inicial de preparação.

Example:
    view = ProgressView()
    view.update_progress(512000, 1024000, "report.pdf")
"""
import time
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar

from ui.components import BentoSpinner
from ui.format_utils import format_time as _format_time

_START_MESSAGES: list[str] = [
    "Começando operação...",
    "Preparando os motores...",
    "Iniciando a restauração dos seus arquivos...",
    "Lendo dados do backup...",
]
_MIDDLE_MESSAGES: list[str] = [
    "Chegamos na metade...",
    "Tudo indo conforme o planejado...",
    "Processando os arquivos...",
    "Restauração a todo vapor...",
]
_END_MESSAGES: list[str] = [
    "Quase lá...",
    "Finalizando a restauração...",
    "Organizando os últimos arquivos...",
    "Falta bem pouquinho...",
]


class ProgressView(QWidget):
    """Tela 4: file copy progress with cancel option and BentoSpinner support.

    Example:
        v = ProgressView()
        v.cancel_requested.connect(worker.request_cancel)
    """

    cancel_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_time: float = 0.0
        self._speed: Optional[float] = None
        self._current_stage: str = ""
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 30)
        layout.setSpacing(14)

        # Title
        title = QLabel("Restaurando arquivos")
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addStretch()

        # Loading Spinner for initial preparation
        self._spinner = BentoSpinner(self)
        layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Progress bar
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(22)
        layout.addWidget(self._bar)

        # Percentage
        self._percent_label = QLabel("0%")
        self._percent_label.setObjectName("BentoValue")
        self._percent_label.setAlignment(Qt.AlignCenter)
        self._percent_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; background: transparent;",
        )
        layout.addWidget(self._percent_label)

        # Status Message Label
        self._status_msg_lbl = QLabel("")
        self._status_msg_lbl.setObjectName("BentoSub")
        self._status_msg_lbl.setAlignment(Qt.AlignCenter)
        self._status_msg_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 500; color: #3B6EA5; background: transparent;",
        )
        layout.addWidget(self._status_msg_lbl)

        # ETA Label
        self._eta_lbl = QLabel("Calculando tempo restante...")
        self._eta_lbl.setObjectName("BentoSub")
        self._eta_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._eta_lbl)

        # Current file
        self._file_label = QLabel("Preparando...")
        self._file_label.setObjectName("BentoSub")
        self._file_label.setAlignment(Qt.AlignCenter)
        self._file_label.setWordWrap(True)
        layout.addWidget(self._file_label)

        layout.addStretch()

        # Cancel button
        self._cancel_btn = QPushButton("Cancelar")
        self._cancel_btn.setObjectName("DangerButton")
        self._cancel_btn.setCursor(Qt.PointingHandCursor)
        self._cancel_btn.setFixedWidth(140)
        self._cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self._cancel_btn, alignment=Qt.AlignCenter)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset to initial state for a fresh copy run."""
        self._bar.setValue(0)
        self._percent_label.setText("0%")
        self._eta_lbl.setText("Calculando tempo restante...")
        self._file_label.setText("Preparando...")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.setText("Cancelar")
        self._spinner.setVisible(True)
        self._start_time = time.perf_counter()
        self._speed = None
        import random
        self._current_stage = "start"
        self._status_msg_lbl.setText(random.choice(_START_MESSAGES))

    def _update_eta(self, bytes_copied: float, total_bytes: float) -> None:
        """Calculate and display the dynamic ETA remaining time."""
        elapsed = time.perf_counter() - self._start_time
        if bytes_copied <= 0.0 or elapsed < 0.5:
            self._eta_lbl.setText("Calculando tempo restante...")
            return
        speed = bytes_copied / elapsed
        self._speed = speed if self._speed is None else 0.15 * speed + 0.85 * self._speed
        rem_bytes = max(0.0, total_bytes - bytes_copied)
        rem_seconds = int(rem_bytes / max(1.0, self._speed))
        self._eta_lbl.setText(f"Tempo restante: {_format_time(rem_seconds)}")

    def update_progress(
        self, bytes_copied: float, total_bytes: float, filename: str
    ) -> None:
        """Update the bar, percentage, dynamic ETA, and filename labels."""
        if total_bytes <= 0.0:
            return
        if bytes_copied > 0.0:
            self._spinner.setVisible(False)
        pct = min(100, int(bytes_copied * 100.0 / total_bytes))
        self._bar.setValue(pct)
        self._percent_label.setText(f"{pct}%")
        self._update_eta(bytes_copied, total_bytes)

        # Dynamic loading messages on stage transition
        if pct < 30:
            new_stage = "start"
        elif pct < 75:
            new_stage = "middle"
        else:
            new_stage = "end"

        if new_stage != self._current_stage:
            self._current_stage = new_stage
            import random
            if new_stage == "start":
                msg = random.choice(_START_MESSAGES)
            elif new_stage == "middle":
                msg = random.choice(_MIDDLE_MESSAGES)
            else:
                msg = random.choice(_END_MESSAGES)
            self._status_msg_lbl.setText(msg)

        short = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        self._file_label.setText(f"Copiando: {short}")

    # ------------------------------------------------------------------
    # Internal Handlers
    # ------------------------------------------------------------------

    def _on_cancel(self) -> None:
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.setText("Cancelando...")
        self.cancel_requested.emit()
