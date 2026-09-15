"""Backup history page. Phase 1: empty state."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel

from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class HistoryPage(BasePage):
    def __init__(self) -> None:
        super().__init__("Backup History")

        card = Card()
        empty = QLabel("No backups yet")
        hint = QLabel("Completed and failed transfers will appear here.")
        hint.setProperty("class", "muted")
        card.add(empty)
        card.add(hint)
        self.body.addWidget(card)

        self.finish()
