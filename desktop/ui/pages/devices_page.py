"""Devices page. Phase 1: empty state; pairing arrives in Phase 4."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton

from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class DevicesPage(BasePage):
    def __init__(self) -> None:
        super().__init__("Devices")

        card = Card("Paired Devices")
        empty = QLabel("No devices paired")
        hint = QLabel("Pairing over your local Wi-Fi network will be "
                      "available here once discovery is enabled.")
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        pair_btn = QPushButton("Pair a Device")
        pair_btn.setProperty("class", "primary")
        pair_btn.setEnabled(False)
        pair_btn.setToolTip("Available in an upcoming build")
        card.add(empty)
        card.add(hint)
        card.add(pair_btn)
        self.body.addWidget(card)

        self.finish()
