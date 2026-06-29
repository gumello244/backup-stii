"""QStackedWidget subclass with fade transitions between views.

Separated from MainWindow for SRP — this file is < 100 lines.

Example:
    stack = FadeStackWidget()
    stack.add_view(welcome_view)
    stack.add_view(analysis_view)
    stack.navigate_to(1)  # fade out 0 → fade in 1
"""
from PyQt5.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtWidgets import QStackedWidget, QGraphicsOpacityEffect, QWidget


class FadeStackWidget(QStackedWidget):
    """QStackedWidget with a cross-fade animation on view changes.

    Example:
        stack = FadeStackWidget(parent)
        stack.add_view(my_widget)
        stack.navigate_to(0)
    """

    _FADE_DURATION_MS = 250

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self._animation: QPropertyAnimation = None

    def add_view(self, widget: QWidget) -> int:
        """Add a view widget and return its index.

        Example:
            idx = stack.add_view(WelcomeView())
        """
        idx = self.addWidget(widget)
        return idx

    def navigate_to(self, index: int) -> None:
        """Transition to the view at *index* with a fade-in effect.

        Example:
            stack.navigate_to(2)
        """
        if index == self.currentIndex():
            return
        target = self.widget(index)
        if target is None:
            return
        self._fade_in(target, index)

    def _fade_in(self, target: QWidget, index: int) -> None:
        """Apply a fade-in opacity animation to the *target* widget."""
        effect = QGraphicsOpacityEffect(target)
        target.setGraphicsEffect(effect)
        effect.setOpacity(0.0)

        self.setCurrentIndex(index)

        self._animation = QPropertyAnimation(effect, b"opacity")
        self._animation.setDuration(self._FADE_DURATION_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)
        # Remove the effect once the animation completes to avoid
        # rendering overhead on the static widget
        self._animation.finished.connect(
            lambda: target.setGraphicsEffect(None),
        )
        self._animation.start()
