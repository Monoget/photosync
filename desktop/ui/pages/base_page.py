"""Common page scaffold: padded scroll area with a title header."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class BasePage(QScrollArea):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget(objectName="appRoot")
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(28, 24, 28, 24)
        self.body.setSpacing(16)

        header = QLabel(title)
        header.setProperty("class", "pageTitle")
        self.body.addWidget(header)

        self.setWidget(content)

    def finish(self) -> None:
        """Call after adding content to push everything to the top."""
        self.body.addStretch(1)
