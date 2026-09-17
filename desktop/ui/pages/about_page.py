"""About page."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class AboutPage(BasePage):
    def __init__(self, app_version: str) -> None:
        super().__init__("About")

        card = Card("PixSynq")
        version = QLabel(f"Version {app_version}")
        desc = QLabel("Automatically back up your Android photos to your "
                      "Windows PC over Wi-Fi.")
        desc.setProperty("class", "muted")
        desc.setWordWrap(True)
        card.add(version)
        card.add(desc)
        self.body.addWidget(card)

        self.finish()
