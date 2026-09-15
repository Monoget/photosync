"""Reusable rounded card container with an optional section title."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    def __init__(self, title: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("class", "card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(20, 16, 20, 16)
        self._layout.setSpacing(10)
        if title:
            label = QLabel(title.upper())
            label.setProperty("class", "cardTitle")
            self._layout.addWidget(label)

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)
