from __future__ import annotations

"""Sub-components for AdminRestoreView: source/RAIZ/profile cards.

Split out of admin_restore_view.py to keep that module focused on the view's
orchestration logic (discovery, search, selection, restore) rather than
widget rendering.
"""

from datetime import datetime

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt5.QtGui import QMouseEvent

from ui.assets import (
    RM_ACCENT, RM_TEXT_MUTED, RM_SURFACE, RM_BORDER,
    RM_HERO_BG, RM_HERO_BORDER,
)
from ui.format_utils import format_bytes as _format_bytes
from services.admin_backup_discovery import AdminBackupSource, UserProfileDetail, PENDING_STATS, ERROR_STATS


class _ElidedLabel(QLabel):
    """QLabel that elides overflowing text and shows the full text as a tooltip.

    Prevents long source names from forcing a horizontal scrollbar onto the
    FONTES DE BACKUP list.
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        super().setText(text)

    def resizeEvent(self, event: object) -> None:
        self._apply_elided_text()
        super().resizeEvent(event)

    def sizeHint(self) -> QSize:
        height = super().sizeHint().height()
        return QSize(0, height)

    def minimumSizeHint(self) -> QSize:
        height = super().minimumSizeHint().height()
        return QSize(0, height)

    def _apply_elided_text(self) -> None:
        # Fall back to the full text if the widget has no real width yet
        # (e.g. before the first layout pass) so the label isn't blanked out.
        width = self.width()
        if width <= 0:
            return
        elided = self.fontMetrics().elidedText(self._full_text, Qt.ElideRight, width)
        super().setText(elided)
        self.setToolTip(self._full_text if elided != self._full_text else "")


class SkeletonCard(QFrame):
    """Placeholder card representing a loading state with shimmer-like aesthetics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"""
            SkeletonCard {{
                background-color: #F7FAFC;
                border: 1px dashed {RM_BORDER};
                border-radius: 8px;
            }}
        """)
        self.setFixedHeight(54)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        t = QLabel("Buscando...", self)
        t.setStyleSheet("color: #CBD5E0; font-size: 12px; font-weight: bold; background: transparent; border: none; margin: 0px; padding: 0px;")
        s = QLabel("Aguardando resposta do disco/rede...", self)
        s.setStyleSheet("color: #E2E8F0; font-size: 11px; background: transparent; border: none; margin: 0px; padding: 0px;")

        layout.addWidget(t)
        layout.addWidget(s)


class SourceCard(QFrame):
    """Clickable card representing one backup source in the left pane."""
    clicked = pyqtSignal(object)  # AdminBackupSource

    def __init__(self, source: AdminBackupSource, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source = source
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
        name_lbl = _ElidedLabel(self.source.name, self)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 12px; background: transparent; border: none; margin: 0px; padding: 0px; padding-right: 2px;"
        )
        name_lbl.setIndent(0)
        tag = "Rede" if self.source.origin == "network" else "Local"
        tag_lbl = QLabel(tag, self)
        tag_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        tag_lbl.setFixedWidth(tag_lbl.sizeHint().width())
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
        self._stats_lbl.setIndent(0)
        layout.addWidget(self._stats_lbl)

    def _stats_text(self) -> str:
        n = len(self.source.profiles)
        word = "perfil" if n == 1 else "perfis"
        # total_bytes is PENDING_STATS until the admin selects this source
        # (exact size is computed lazily — see AdminSourceDetailWorker).
        if self.source.total_bytes == PENDING_STATS:
            return f"{n} {word}"
        return f"{_format_bytes(self.source.total_bytes)} • {n} {word}"

    def update_source(self, source: AdminBackupSource) -> None:
        """Refresh display after lazily-loaded exact sizes arrive."""
        self.source = source
        self._stats_lbl.setText(self._stats_text())

    def update_style(self) -> None:
        if self.selected:
            self.setStyleSheet(f"""
                SourceCard {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                SourceCard {{
                    background-color: {RM_SURFACE};
                    border: 1px solid {RM_BORDER};
                    border-radius: 8px;
                }}
                SourceCard:hover {{ background-color: #EDF2F7; }}
            """)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self.source)
        super().mousePressEvent(event)


class RaizDetailCard(QFrame):
    """Toggle-able card showing RAIZ folder stats above the profiles list."""
    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.selected = False
        self.raiz_data = None
        self._build()

    def _build(self) -> None:
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(76)
        self.update_style()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)

        self._title_lbl = QLabel("PASTA RAIZ", self)
        self._title_lbl.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED};"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        lay.addWidget(self._title_lbl)

        self._val_lbl = QLabel("", self)
        self._val_lbl.setStyleSheet(
            f"font-size: 18px; font-weight: 700; color: {RM_ACCENT};"
            " background: transparent; border: none;"
        )
        lay.addWidget(self._val_lbl)

        self._sub_lbl = QLabel("", self)
        self._sub_lbl.setStyleSheet(
            f"font-size: 11px; color: {RM_TEXT_MUTED}; background: transparent; border: none;"
        )
        lay.addWidget(self._sub_lbl)

    def populate(self, raiz_data: object | None) -> None:
        self.raiz_data = raiz_data
        if raiz_data and raiz_data.file_count == ERROR_STATS:
            self._val_lbl.setText("Erro ao calcular")
            self._sub_lbl.setText("Falha na leitura do disco/rede")
            self.setCursor(Qt.ArrowCursor)
        elif raiz_data and raiz_data.file_count == PENDING_STATS:
            # Exact size not loaded yet — see AdminSourceDetailRunnable.
            self._val_lbl.setText("Calculando...")
            self._sub_lbl.setText("")
            self.setCursor(Qt.PointingHandCursor)
        elif raiz_data:
            self._val_lbl.setText(_format_bytes(raiz_data.size_bytes))
            self._sub_lbl.setText(f"{raiz_data.file_count} arquivos, {raiz_data.dir_count} pastas")
            self.setCursor(Qt.PointingHandCursor)
        else:
            self._val_lbl.setText("")
            self._sub_lbl.setText("")

    def update_style(self) -> None:
        if self.selected:
            self.setStyleSheet(f"""
                RaizDetailCard {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 10px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                RaizDetailCard {{
                    background-color: {RM_SURFACE};
                    border: 1px solid {RM_BORDER};
                    border-radius: 10px;
                }}
                RaizDetailCard:hover {{ background-color: #EDF2F7; }}
            """)

    def toggle(self) -> None:
        if self.raiz_data:
            self.selected = not self.selected
            self.update_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self.raiz_data:
            self.clicked.emit()
        super().mousePressEvent(event)


class ProfileRow(QFrame):
    """Toggle-able row for a single user profile backup (multi-select)."""
    clicked = pyqtSignal(object)  # UserProfileDetail

    def __init__(self, profile: UserProfileDetail, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profile = profile
        self.selected = False
        self._build()

    def _build(self) -> None:
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self.update_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        name_lbl = QLabel(self.profile.name, self)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; background: transparent; border: none;"
        )
        dt = datetime.fromtimestamp(self.profile.modified_time)
        date_lbl = QLabel(dt.strftime("%d/%m/%Y"), self)
        date_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 11px; background: transparent; border: none;"
        )
        # Exact size not loaded yet — see AdminSourceDetailRunnable.
        if self.profile.file_count == ERROR_STATS:
            size_text = "Erro"
            size_color = "#E53E3E"
        elif self.profile.file_count == PENDING_STATS:
            size_text = "Calculando..."
            size_color = RM_TEXT_MUTED
        else:
            size_text = _format_bytes(self.profile.size_bytes)
            size_color = RM_ACCENT

        size_lbl = QLabel(size_text, self)
        size_lbl.setStyleSheet(
            f"font-weight: bold; color: {size_color}; font-size: 12px; background: transparent; border: none;"
        )
        layout.addWidget(name_lbl)
        layout.addWidget(date_lbl)
        layout.addStretch()
        layout.addWidget(size_lbl)

    def update_style(self) -> None:
        if self.selected:
            self.setStyleSheet(f"""
                ProfileRow {{
                    background-color: {RM_HERO_BG};
                    border: 2px solid {RM_HERO_BORDER};
                    border-radius: 6px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                ProfileRow {{
                    background-color: {RM_SURFACE};
                    border: 1px solid {RM_BORDER};
                    border-radius: 6px;
                }}
                ProfileRow:hover {{ border-color: #bbbbbb; }}
            """)

    def toggle(self) -> None:
        self.selected = not self.selected
        self.update_style()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit(self.profile)
        super().mousePressEvent(event)
