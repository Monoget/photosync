"""Dashboard page: connection, backup stats, destination, last backup."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QLabel, QProgressBar

from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.database.db import PhotoStore
from ui.pages.base_page import BasePage
from ui.widgets.card import Card


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


def _format_time(iso: str | None) -> str:
    if not iso:
        return "Never"
    try:
        moment = datetime.fromisoformat(iso).astimezone()
    except ValueError:
        return "Never"
    if moment.date() == datetime.now().astimezone().date():
        return f"Today • {moment.strftime('%H:%M')}"
    return moment.strftime("%Y-%m-%d • %H:%M")


class DashboardPage(BasePage):
    def __init__(
        self,
        settings: SettingsStore | None = None,
        photo_store: PhotoStore | None = None,
    ) -> None:
        super().__init__("Dashboard")
        self._settings = settings
        self._photos = photo_store
        self._network_count = 0

        device_card = Card("Connected Device")
        self.device_status = QLabel("No device paired yet")
        self.network_status = QLabel("Searching for devices on your Wi-Fi network…")
        self.network_status.setProperty("class", "muted")
        self.network_status.setWordWrap(True)
        device_card.add(self.device_status)
        device_card.add(self.network_status)
        self.body.addWidget(device_card)

        backup_card = Card("Backup")
        self.backup_stats = QLabel()
        self.backup_stats.setProperty("class", "statValue")
        self.backup_bytes = QLabel()
        self.backup_bytes.setProperty("class", "muted")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.hide()
        backup_card.add(self.backup_stats)
        backup_card.add(self.backup_bytes)
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
        self.last_backup = QLabel("Never")
        self.last_backup.setProperty("class", "muted")
        last_card.add(self.last_backup)
        self.body.addWidget(last_card)

        self.finish()
        self.refresh_stats()

    # -- Slots ----------------------------------------------------------

    def refresh_stats(self) -> None:
        if self._photos is None:
            self.backup_stats.setText("0 Photos")
            self.backup_bytes.setText("Nothing backed up yet")
            return
        count = self._photos.completed_count()
        self.backup_stats.setText(f"{count:,} Photo{'s' if count != 1 else ''}")
        if count:
            self.backup_bytes.setText(_format_bytes(self._photos.total_bytes()))
        else:
            self.backup_bytes.setText("Nothing backed up yet")
        self.last_backup.setText(_format_time(self._photos.last_completed_at()))

    def on_photo_received(self, _filename: str) -> None:
        self.refresh_stats()

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
