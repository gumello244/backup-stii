from __future__ import annotations

"""AdminRestoreView — search, select and scope backup sources for admin restoration.

Layout:
  - While discovering: full-area centered spinner with status text (no cards).
  - After discovery: horizontal split — left (FONTES DE BACKUP) | right (details).
  - Footer: [Voltar]  ——stretch——  [Continuar]  [search input] [🔍 btn]

Selection model:
  - Clicking a SourceCard selects it; details pane becomes visible.
  - Clicking the SourceCard again (or with no sub-selection) means "restore all".
  - RAIZ card and each ProfileRow are individually toggle-able (multi-select).
  - Next-button label is driven by the current selection set.
"""

import logging
from typing import Optional

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame,
    QStackedWidget,
)

from ui.assets import RM_TEXT_MUTED, RM_BORDER, RM_SURFACE
from ui.components import BentoSpinner
from ui.workers import AdminDiscoverSourcesWorker, AdminPrepareRestoreWorker, AdminSourceDetailWorker
from ui.views.admin_restore_cards import SourceCard, RaizDetailCard, ProfileRow
from services.admin_backup_discovery import AdminBackupSource, UserProfileDetail, PENDING_STATS
from services.backup_discovery import extract_machine_id
from services.backup_merger import MergedFileSet, group_by_folder

logger = logging.getLogger(__name__)

# Stack page indices
_PAGE_SEARCHING = 0
_PAGE_RESULTS   = 1


def _source_sort_key(src: AdminBackupSource) -> float:
    """Return newest profile mtime for sorting (newest-first)."""
    return max((p.modified_time for p in src.profiles), default=0.0)


# Search-stage status text, keyed by services.admin_backup_discovery stage ids.
_STAGE_LABELS = {
    "machine": "Buscando pela máquina...",
    "current_user": "Buscando pelo usuário atual...",
    "machine_users": "Buscando pelos usuários da máquina...",
}


# ---------------------------------------------------------------------------
# Main view
# ---------------------------------------------------------------------------

class AdminRestoreView(QWidget):
    """Admin backup restoration view with incremental discovery and multi-select scope.

    Example:
        view = AdminRestoreView()
        view.back_requested.connect(go_back)
        view.next_requested.connect(proceed_to_confirm)
        view.start_discovery()
    """

    back_requested = pyqtSignal()
    next_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sources: list[AdminBackupSource] = []
        self.cards: list[SourceCard] = []
        self.selected_source: Optional[AdminBackupSource] = None
        self.profile_rows: list[ProfileRow] = []
        self.worker: Optional[AdminDiscoverSourcesWorker] = None
        self.prep_worker: Optional[AdminPrepareRestoreWorker] = None
        self._detail_worker: Optional[AdminSourceDetailWorker] = None
        self._current_query: Optional[str] = None

        self._init_ui()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 20, 40, 20)
        root.setSpacing(10)

        title = QLabel("Restauração de Backups", self)
        title.setObjectName("ViewTitle")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        # Stacked widget: page 0 = searching state, page 1 = results split
        self._stack = QStackedWidget(self)
        self._build_searching_page()
        self._build_results_page()
        root.addWidget(self._stack, stretch=1)

        self._init_footer(root)

    def _build_searching_page(self) -> None:
        """Page 0 — centered spinner + status label during discovery."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(12)

        spinner_row = QHBoxLayout()
        spinner_row.setAlignment(Qt.AlignCenter)
        spinner_row.setSpacing(10)

        self._spinner = BentoSpinner(page)
        self._status_lbl = QLabel("Buscando backups...", page)
        self._status_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 13px; background: transparent;"
        )
        spinner_row.addWidget(self._spinner)
        spinner_row.addWidget(self._status_lbl)
        lay.addLayout(spinner_row)

        self._stack.addWidget(page)   # index 0

    def _build_results_page(self) -> None:
        """Page 1 — horizontal split: sources list | details pane."""
        page = QWidget()
        split = QHBoxLayout(page)
        split.setContentsMargins(0, 0, 0, 0)
        split.setSpacing(12)

        self._init_left_pane(split)
        self._init_right_pane(split)

        self._stack.addWidget(page)   # index 1

    def _init_left_pane(self, split: QHBoxLayout) -> None:
        left = QFrame()
        left.setObjectName("SurfaceCard")
        left.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px;"
            f" background: #FFFFFF; }}"
        )
        lay = QVBoxLayout(left)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(6)
        hdr = QLabel("FONTES DE BACKUP", left)
        hdr.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED};"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        hdr_row.addWidget(hdr)

        self._header_spinner = BentoSpinner(left, size=14)
        self._header_spinner.setVisible(False)
        hdr_row.addWidget(self._header_spinner)
        hdr_row.addStretch()
        lay.addLayout(hdr_row)

        self._stage_lbl = QLabel("", left)
        self._stage_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 10px; background: transparent; border: none;"
        )
        self._stage_lbl.setVisible(False)
        lay.addWidget(self._stage_lbl)

        scroll = QScrollArea(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background: transparent;")

        self.sources_container = QWidget(scroll)
        self.sources_container.setStyleSheet("background: transparent;")
        self.sources_layout = QVBoxLayout(self.sources_container)
        self.sources_layout.setContentsMargins(0, 0, 0, 0)
        self.sources_layout.setSpacing(6)
        self.sources_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.sources_container)
        lay.addWidget(scroll)

        split.addWidget(left, stretch=2)

    def _init_right_pane(self, split: QHBoxLayout) -> None:
        """Right details pane — RAIZ card (standalone, above profiles box)."""
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)

        # RAIZ card — sits independently above the profiles container
        self.raiz_card = RaizDetailCard(right)
        self.raiz_card.clicked.connect(self._on_raiz_toggled)
        self.raiz_card.setVisible(False)
        right_lay.addWidget(self.raiz_card)

        # Profiles container (framed box)
        profiles_frame = QFrame(right)
        profiles_frame.setObjectName("SurfaceCard")
        profiles_frame.setStyleSheet(
            f"QFrame#SurfaceCard {{ border: 1px solid {RM_BORDER}; border-radius: 10px;"
            f" background: #FFFFFF; }}"
        )
        profiles_lay = QVBoxLayout(profiles_frame)
        profiles_lay.setContentsMargins(8, 8, 8, 8)
        profiles_lay.setSpacing(6)

        self.profiles_title = QLabel("PERFIS DE USUÁRIOS", profiles_frame)
        self.profiles_title.setStyleSheet(
            f"font-size: 9px; font-weight: 800; color: {RM_TEXT_MUTED};"
            " letter-spacing: 1px; background: transparent; border: none;"
        )
        profiles_lay.addWidget(self.profiles_title)

        self.profiles_scroll = QScrollArea(profiles_frame)
        self.profiles_scroll.setWidgetResizable(True)
        self.profiles_scroll.setFrameShape(QFrame.NoFrame)
        self.profiles_scroll.setStyleSheet("border: none; background: transparent;")

        self.profiles_container = QWidget(self.profiles_scroll)
        self.profiles_container.setStyleSheet("background: transparent;")
        self.profiles_layout = QVBoxLayout(self.profiles_container)
        self.profiles_layout.setContentsMargins(0, 0, 0, 0)
        self.profiles_layout.setSpacing(4)
        self.profiles_layout.setAlignment(Qt.AlignTop)
        self.profiles_scroll.setWidget(self.profiles_container)
        profiles_lay.addWidget(self.profiles_scroll, stretch=1)

        right_lay.addWidget(profiles_frame, stretch=1)

        # Right side starts hidden; placeholder shown until a source is selected
        self._right_widget = right
        self._right_widget.setVisible(False)

        # Placeholder shown in the right area when no source is selected
        self._right_placeholder = QWidget()
        ph_lay = QVBoxLayout(self._right_placeholder)
        ph_lay.setAlignment(Qt.AlignCenter)
        ph_lbl = QLabel("Selecione uma fonte à esquerda\npara ver seus detalhes.", self._right_placeholder)
        ph_lbl.setAlignment(Qt.AlignCenter)
        ph_lbl.setWordWrap(True)
        ph_lbl.setStyleSheet(
            f"color: {RM_TEXT_MUTED}; font-size: 13px; background: transparent; border: none;"
        )
        ph_lay.addWidget(ph_lbl)

        split.addWidget(self._right_placeholder, stretch=3)
        split.addWidget(self._right_widget, stretch=3)

    def _init_footer(self, root: QVBoxLayout) -> None:
        """Footer: [Voltar] [Continuar] —stretch— [search input] [btn].

        Voltar/Continuar are left-aligned so they sit directly under the
        FONTES DE BACKUP card's left edge.
        """
        row = QHBoxLayout()
        row.setSpacing(8)

        self._back_btn = QPushButton("Voltar", self)
        self._back_btn.setObjectName("SecondaryButton")
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.clicked.connect(self.back_requested.emit)

        self._next_btn = QPushButton("Continuar", self)
        self._next_btn.setObjectName("PrimaryButton")
        self._next_btn.setCursor(Qt.PointingHandCursor)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._on_next_clicked)

        row.addWidget(self._back_btn)
        row.addWidget(self._next_btn)
        row.addStretch()

        # Compact search controls at far right
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Usuário ou hostname...")
        self.search_input.setFixedWidth(180)
        self.search_input.setStyleSheet(
            "padding: 4px 8px; border: 1px solid #DDDDDD; border-radius: 6px; font-size: 12px;"
        )
        self.search_input.returnPressed.connect(self._on_search_clicked)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.search_btn = QPushButton(self)
        self.search_btn.setToolTip("Buscar")
        self.search_btn.setFixedSize(30, 30)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        # Minimalist SVG magnifying-glass icon via Qt standard pixmap
        self.search_btn.setIcon(
            self.style().standardIcon(self.style().SP_FileDialogContentsView)
        )
        self.search_btn.setIconSize(QSize(16, 16))
        self.search_btn.setStyleSheet(
            f"QPushButton {{ background-color: {RM_SURFACE}; border: 1px solid #DDDDDD;"
            f" border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: #EDF2F7; }}"
        )
        self.search_btn.clicked.connect(self._on_search_clicked)

        row.addWidget(self.search_input)
        row.addWidget(self.search_btn)

        root.addLayout(row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_discovery(self, query: Optional[str] = None) -> None:
        """Begin incremental background scan and switch to searching state."""
        self._detach_worker()
        self._current_query = query
        self._clear_sources()
        self._hide_details()
        self._set_status("Buscando backups...")
        self._stack.setCurrentIndex(_PAGE_SEARCHING)
        self._spinner.setVisible(True)
        self._header_spinner.setVisible(True)
        self._stage_lbl.setVisible(True)

        self.worker = AdminDiscoverSourcesWorker(query)
        self.worker.source_found.connect(self._on_source_found)
        self.worker.stage_changed.connect(self._on_stage_changed)
        self.worker.finished.connect(self._on_discovery_finished)
        self.worker.start()

    def _detach_worker(self) -> None:
        """Stop and sever ties to a still-running previous search.

        Without request_cancel(), the old QThread keeps scanning the network
        share in the background purely to be discarded. Without
        disconnecting its signals, any results it emits before noticing the
        cancellation would still leak into the new search's results list.
        """
        if self.worker is None:
            return
        self.worker.request_cancel()
        for signal in (self.worker.source_found, self.worker.stage_changed, self.worker.finished):
            try:
                signal.disconnect()
            except TypeError:
                pass  # already disconnected

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    def _clear_sources(self) -> None:
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()
        self.sources.clear()
        self.selected_source = None

    def _hide_details(self) -> None:
        self._right_widget.setVisible(False)
        self._right_placeholder.setVisible(True)
        self.raiz_card.populate(None)
        self.raiz_card.selected = False
        self.raiz_card.update_style()
        self.raiz_card.setVisible(False)
        self._clear_profile_rows()
        self._update_next_button()

    def _show_details(self) -> None:
        self._right_placeholder.setVisible(False)
        self._right_widget.setVisible(True)

    def _clear_profile_rows(self) -> None:
        for r in self.profile_rows:
            r.deleteLater()
        self.profile_rows.clear()

    def _selected_profiles(self) -> list[UserProfileDetail]:
        return [r.profile for r in self.profile_rows if r.selected]

    def _raiz_selected(self) -> bool:
        return self.raiz_card.selected and bool(self.raiz_card.raiz_data)

    def _update_next_button(self) -> None:
        """Derive next-button label and enable-state from current selection."""
        if not self.selected_source:
            self._next_btn.setEnabled(False)
            self._next_btn.setText("Continuar")
            return

        raiz_sel = self._raiz_selected()
        profiles_sel = self._selected_profiles()
        any_sub = raiz_sel or profiles_sel

        if not any_sub:
            # Source selected but nothing drilled into — full restore
            self._next_btn.setText("Restaurar tudo")
            self._next_btn.setEnabled(True)
            return

        parts: list[str] = []
        if raiz_sel:
            parts.append("RAIZ")
        if len(profiles_sel) == 1:
            parts.append(profiles_sel[0].name)
        elif len(profiles_sel) > 1:
            parts.append("usuários")

        label = " + ".join(parts)
        self._next_btn.setText(f"Restaurar {label}")
        self._next_btn.setEnabled(True)

    def _compute_scope(self) -> tuple[str, Optional[str]]:
        """Return (scope_key, profile_name_or_none) for file compilation.

        Scope key matches what compile_admin_restore_files expects:
        'all', 'raiz', 'profile'.  Multi-select is mapped to 'all' with
        selective filtering handled by the caller.
        """
        raiz_sel = self._raiz_selected()
        profiles = self._selected_profiles()

        if not raiz_sel and not profiles:
            return ("all", None)
        if raiz_sel and not profiles:
            return ("raiz", None)
        if not raiz_sel and len(profiles) == 1:
            return ("profile", profiles[0].name)
        # Mixed or multi-profile → compile everything then filter in _on_prepare_finished
        return ("all", None)

    # ------------------------------------------------------------------
    # Slots — discovery
    # ------------------------------------------------------------------

    def _on_source_found(self, src: AdminBackupSource) -> None:
        card = SourceCard(src, self.sources_container)
        card.clicked.connect(self._on_source_card_clicked)
        self.sources_layout.addWidget(card)
        self.sources.append(src)
        self.cards.append(card)
        self._sort_cards()
        self._apply_client_filter(self.search_input.text().strip().lower())
        # Switch to results page on first result
        if self._stack.currentIndex() == _PAGE_SEARCHING:
            self._stack.setCurrentIndex(_PAGE_RESULTS)

    def _sort_cards(self) -> None:
        self.cards.sort(key=lambda c: _source_sort_key(c.source), reverse=True)
        for i in reversed(range(self.sources_layout.count())):
            item = self.sources_layout.takeAt(i)
            if item.widget():
                item.widget().hide()
        for card in self.cards:
            self.sources_layout.addWidget(card)
            card.show()

    def _on_stage_changed(self, stage: str) -> None:
        if stage == "query" and self._current_query:
            text = f'Buscando por "{self._current_query}"...'
        else:
            text = _STAGE_LABELS.get(stage, "Buscando...")
        self._stage_lbl.setText(text)

    def _on_discovery_finished(self) -> None:
        self._header_spinner.setVisible(False)
        self._stage_lbl.setVisible(False)
        self._stage_lbl.setText("")
        if not self.sources:
            self._spinner.setVisible(False)
            self._set_status("Nenhum backup encontrado. Use a busca abaixo.")
            self._stack.setCurrentIndex(_PAGE_SEARCHING)

    def _on_search_clicked(self) -> None:
        q = self.search_input.text().strip()
        self.start_discovery(q if q else None)

    def _on_search_text_changed(self, text: str) -> None:
        """Filter already-discovered sources client-side as the user types.

        Only the search button (or Enter) triggers a real backend scan —
        typing must never re-hit the network per keystroke.
        """
        self._apply_client_filter(text.strip().lower())

    def _apply_client_filter(self, query: str) -> None:
        live_cards = []
        for card in self.cards:
            try:
                card.setVisible(not query or self._source_matches_query(card.source, query))
            except RuntimeError:
                # Underlying Qt widget was already deleted (deleteLater from
                # a prior search still pending) — drop the stale reference.
                continue
            live_cards.append(card)
        self.cards = live_cards

    @staticmethod
    def _source_matches_query(source: AdminBackupSource, query: str) -> bool:
        # Mirror scan_admin_backups' matching: admins often search by
        # hostname (e.g. "25STI3T125678") rather than the backup folder's
        # own naming convention, so also match on the extracted machine id.
        terms = {query}
        machine_id = extract_machine_id(query).lower()
        if machine_id:
            terms.add(machine_id)

        name_lower = source.name.lower()
        if any(term in name_lower for term in terms):
            return True
        return any(term in p.name.lower() for p in source.profiles for term in terms)

    # ------------------------------------------------------------------
    # Slots — selection (multi-select toggle model)
    # ------------------------------------------------------------------

    def _on_source_card_clicked(self, source: AdminBackupSource) -> None:
        """Select source; reset all sub-selections."""
        self.selected_source = source
        for card in self.cards:
            card.selected = (card.source.path == source.path)
            card.update_style()

        self._populate_details(source)
        self._show_details()
        self._update_next_button()

        if source.total_bytes == PENDING_STATS:
            # Discovery only proved this source has restorable content —
            # exact sizes weren't computed to keep a broad search cheap.
            # Fetch them now that the admin actually picked this one.
            self._detail_worker = AdminSourceDetailWorker(source)
            self._detail_worker.finished.connect(self._on_source_details_loaded)
            self._detail_worker.start()

    def _populate_details(self, source: AdminBackupSource) -> None:
        """(Re)build the RAIZ card and profile rows for *source*."""
        self.raiz_card.populate(source.raiz)
        self.raiz_card.selected = False
        self.raiz_card.update_style()
        self.raiz_card.setVisible(bool(source.raiz))

        self._clear_profile_rows()
        for profile in sorted(source.profiles, key=lambda p: p.modified_time, reverse=True):
            row = ProfileRow(profile, self.profiles_container)
            row.clicked.connect(self._on_profile_toggled)
            self.profiles_layout.addWidget(row)
            self.profile_rows.append(row)

    def _replace_source(self, detailed: AdminBackupSource) -> None:
        """Swap the placeholder source for its fully-sized counterpart."""
        for i, s in enumerate(self.sources):
            if s.path == detailed.path:
                self.sources[i] = detailed
                break
        for card in self.cards:
            if card.source.path == detailed.path:
                card.update_source(detailed)
                break

    def _on_source_details_loaded(self, detailed: AdminBackupSource) -> None:
        self._replace_source(detailed)
        if not self.selected_source or self.selected_source.path != detailed.path:
            return  # admin already moved on to a different source

        selected_names = {r.profile.name for r in self.profile_rows if r.selected}
        raiz_was_selected = self.raiz_card.selected
        self.selected_source = detailed
        self._populate_details(detailed)
        if raiz_was_selected and detailed.raiz:
            self.raiz_card.selected = True
            self.raiz_card.update_style()
        for row in self.profile_rows:
            if row.profile.name in selected_names:
                row.toggle()
        self._update_next_button()

    def _on_raiz_toggled(self) -> None:
        self.raiz_card.toggle()
        self._update_next_button()

    def _on_profile_toggled(self, profile: UserProfileDetail) -> None:
        for row in self.profile_rows:
            if row.profile.name == profile.name:
                row.toggle()
                break
        self._update_next_button()

    # ------------------------------------------------------------------
    # Slots — navigation
    # ------------------------------------------------------------------

    def _on_next_clicked(self) -> None:
        if not self.selected_source:
            return

        scope, profile_name = self._compute_scope()

        self.search_btn.setEnabled(False)
        self._back_btn.setEnabled(False)
        self._next_btn.setEnabled(False)
        self._next_btn.setText("Processando...")

        self.prep_worker = AdminPrepareRestoreWorker(
            self.selected_source, scope, profile_name
        )
        self.prep_worker.finished.connect(self._on_prepare_finished)
        self.prep_worker.start()

    def _on_prepare_finished(self, files: list) -> None:
        """Filter compiled files to match multi-select, then hand off to ConfirmView."""
        self.search_btn.setEnabled(True)
        self._back_btn.setEnabled(True)
        self._update_next_button()

        raiz_sel = self._raiz_selected()
        sel_profiles = {p.name for p in self._selected_profiles()}
        any_sub = raiz_sel or sel_profiles

        # Filter file list when a partial selection was made
        if any_sub:
            files = [
                f for f in files
                if (f.dest_folder == "RAIZ" and raiz_sel)
                or (f.dest_folder != "RAIZ" and f.target_profile in sel_profiles)
                or (f.dest_folder != "RAIZ" and not sel_profiles)
            ]

        scope_parts: list[str] = []
        if raiz_sel:
            scope_parts.append("RAIZ")
        if sel_profiles:
            scope_parts.extend(sorted(sel_profiles))
        scope_lbl = " + ".join(scope_parts) if scope_parts else "Tudo"
        summary = f"{self.selected_source.name} ({scope_lbl})"

        by_folder = group_by_folder(files)
        total = sum(f.size_bytes for f in files)
        merged = MergedFileSet(
            files=files,
            total_bytes=total,
            by_folder=by_folder,
            source_summary=summary,
        )

        win = self.window()
        if hasattr(win, "_state"):
            win._state.merged = merged
            win._state.sources = [self.selected_source]

        self.next_requested.emit()
