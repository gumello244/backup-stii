from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class BentoBox(QFrame):
    """A card container displaying a title, value, and subtitle using bento styles.

    Usage Example:
        box = BentoBox("TAMANHO TOTAL", "2.3 GB", "Volume consolidado", "default")
        layout.addWidget(box)
    """

    def __init__(
        self,
        title: str,
        value: str,
        subtitle: str,
        variant: str = "default",
        alignment: Qt.Alignment = Qt.AlignLeft | Qt.AlignVCenter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._variant: str = variant
        self._init_ui(title, value, subtitle, alignment)
        self.set_variant(variant)

    def _init_ui(
        self,
        title: str,
        value: str,
        subtitle: str,
        alignment: Qt.Alignment,
    ) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)
        layout.setAlignment(alignment)

        self._title_lbl = QLabel(title, self)
        self._title_lbl.setObjectName("BentoTitle")

        self._val_lbl = QLabel(value, self)
        self._val_lbl.setObjectName("BentoValue")

        self._sub_lbl = QLabel(subtitle, self)
        self._sub_lbl.setObjectName("BentoSub")
        self._sub_lbl.setVisible(bool(subtitle))

        # Background transparent prevents white leakage on non-default cards
        self._title_lbl.setStyleSheet("background: transparent;")
        self._val_lbl.setStyleSheet("background: transparent;")
        self._sub_lbl.setStyleSheet("background: transparent;")

        self._apply_alignment(alignment)

        layout.addWidget(self._title_lbl)
        layout.addWidget(self._val_lbl)
        layout.addWidget(self._sub_lbl)

    def _apply_alignment(self, alignment: Qt.Alignment) -> None:
        """Apply horizontal alignment to internal labels based on card alignment."""
        horiz = Qt.AlignLeft
        if alignment & Qt.AlignHCenter:
            horiz = Qt.AlignHCenter
        elif alignment & Qt.AlignRight:
            horiz = Qt.AlignRight

        self._title_lbl.setAlignment(horiz | Qt.AlignVCenter)
        self._val_lbl.setAlignment(horiz | Qt.AlignVCenter)
        self._sub_lbl.setAlignment(horiz | Qt.AlignVCenter)


    def update_content(self, title: str, value: str, subtitle: str) -> None:
        """Update text contents of the bento card labels and toggle visibility."""
        self._title_lbl.setText(title)
        self._val_lbl.setText(value)
        self._sub_lbl.setText(subtitle)
        self._sub_lbl.setVisible(bool(subtitle))

    def set_variant(self, variant: str) -> None:
        """Change the variant and refresh QSS styling rules.

        Raises:
            ValueError: If the variant is not valid.
        """
        valid_variants = {"default", "hero", "success", "danger"}
        if variant not in valid_variants:
            raise ValueError(
                f"Invalid variant {variant!r}, expected one of: {valid_variants}"
            )

        self._variant = variant

        name_map = {
            "default": "BentoCard",
            "hero": "BentoCardHero",
            "success": "BentoCardSuccess",
            "danger": "BentoCardDanger",
        }
        self.setObjectName(name_map[variant])

        val_name_map = {
            "default": "BentoValue",
            "hero": "BentoValueHero",
            "success": "BentoValueSuccess",
            "danger": "BentoValueDanger",
        }
        self._val_lbl.setObjectName(val_name_map[variant])

        # Force Qt style system to re-evaluate stylesheet rules
        self.style().unpolish(self)
        self.style().polish(self)
        self._val_lbl.style().unpolish(self._val_lbl)
        self._val_lbl.style().polish(self._val_lbl)
        self.update()
