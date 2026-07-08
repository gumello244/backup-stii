from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import QWidget

from ui.assets import RM_ACCENT


class BentoSpinner(QWidget):
    """Simple animated loading spinner styled with Remos signature accent.

    Usage Example:
        spinner = BentoSpinner(self)
        layout.addWidget(spinner)
    """

    def __init__(self, parent: QWidget | None = None, size: int = 28) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle: int = 0
        self._timer: QTimer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._timer.start(50)

    def _rotate(self) -> None:
        """Rotate the spinner angle by 30 degrees if visible."""
        if self.isVisible():
            self._angle = (self._angle + 30) % 360
            self.update()

    def hideEvent(self, event: object) -> None:
        """Stop the rotation timer when hidden."""
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: object) -> None:
        """Start the rotation timer when shown."""
        self._timer.start(50)
        super().showEvent(event)

    def paintEvent(self, event: object) -> None:
        """Paint the animated arc spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._angle)
        
        pen_width = max(1.5, self.width() / 11)
        pen = QPen(QColor(RM_ACCENT), pen_width)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        radius = self.width() / 2 - pen_width
        painter.drawArc(int(-radius), int(-radius), int(radius * 2), int(radius * 2), 0, 270 * 16)
