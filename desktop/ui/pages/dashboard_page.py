"""Dashboard page. Phase 1: static shell with honest empty states."""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QProgressBar

from infrastructure.configuration.settings_store import SettingsStore
from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class DashboardPage(BasePage):
    def __init__(self, settings: SettingsStore | None = None) -> None:
        super().__init__("Dashboard")
        self._settings = settings

        device_card = Card("Connected Device")
        no_device = QLabel("No device paired yet")
        hint = QLabel("Install PhotoSync on your Android phone and pair it "
                      "from the Devices page to start backing up photos.")
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        device_card.add(no_device)
        device_card.add(hint)
        self.body.addWidget(device_card)

        backup_card = Card("Backup")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        status = QLabel("Waiting for a paired device")
        status.setProperty("class", "muted")
        backup_card.add(status)
        backup_card.add(self.progress)
        self.body.addWidget(backup_card)

        dest_card = Card("Destination")
        dest_dir = settings.destination_dir if settings else None
        dest = QLabel(str(dest_dir) if dest_dir else "Not configured")
        if not dest_dir:
            dest.setProperty("class", "muted")
        dest_card.add(dest)
        self.body.addWidget(dest_card)

        last_card = Card("Last Backup")
        never = QLabel("Never")
        never.setProperty("class", "muted")
        last_card.add(never)
        self.body.addWidget(last_card)

        self.finish()
