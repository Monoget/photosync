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
        self.device_status = QLabel("No device paired yet")
        self.network_status = QLabel("Searching for devices on your Wi-Fi network…")
        self.network_status.setProperty("class", "muted")
        self.network_status.setWordWrap(True)
        device_card.add(self.device_status)
        device_card.add(self.network_status)
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
        self._network_count = 0

    # -- Slots (connected to DiscoveryService) --------------------------

    def on_announcing_changed(self, announcing: bool) -> None:
        if not announcing:
            self.network_status.setText(
                "Discovery is unavailable — check your network connection."
            )

    def on_network_count_changed(self, count: int) -> None:
        self._network_count = count
        if count == 0:
            self.network_status.setText(
                "Searching for devices on your Wi-Fi network…"
            )
        elif count == 1:
            self.network_status.setText(
                "1 device on your network — pair it from the Devices page."
            )
        else:
            self.network_status.setText(
                f"{count} devices on your network — pair one from the Devices page."
            )
