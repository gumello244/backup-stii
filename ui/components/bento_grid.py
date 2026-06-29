from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QWidget


class BentoGrid(QWidget):
    """A layout widget that displays BentoBox cards in a grid.

    Usage Example:
        grid = BentoGrid(spacing=8)
        grid.add_card(card, 0, 0, rowspan=2, colspan=1)
    """

    def __init__(self, spacing: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing)

    def add_card(
        self,
        widget: QWidget,
        row: int,
        col: int,
        rowspan: int = 1,
        colspan: int = 1,
    ) -> None:
        """Add a widget card to the grid layout with spanning options."""
        self._layout.addWidget(widget, row, col, rowspan, colspan)

    def clear(self) -> None:
        """Remove and delete all cards from the grid."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
