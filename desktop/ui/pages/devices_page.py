"""Devices page: live list of PhotoSync devices seen on the network.

Pairing arrives in Phase 4; until then devices show as "Not paired".
"""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.models.device import DiscoveredDevice
from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class DevicesPage(BasePage):
    def __init__(self) -> None:
        super().__init__("Devices")
        self._devices: dict[str, DiscoveredDevice] = {}

        network_card = Card("On Your Network")
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        self._empty_label = QLabel("Searching for devices on your Wi-Fi network…")
        self._empty_label.setProperty("class", "muted")
        self._list_layout.addWidget(self._empty_label)
        network_card.add(self._list_host)
        self.body.addWidget(network_card)

        paired_card = Card("Paired Devices")
        none_paired = QLabel("No devices paired")
        hint = QLabel("Pairing with a QR code arrives in an upcoming build.")
        hint.setProperty("class", "muted")
        hint.setWordWrap(True)
        paired_card.add(none_paired)
        paired_card.add(hint)
        self.body.addWidget(paired_card)

        self.finish()

    # -- Slots (connected to DiscoveryService) --------------------------

    def on_device_found(self, device: DiscoveredDevice) -> None:
        self._devices[device.service_name] = device
        self._rebuild()

    def on_device_lost(self, service_name: str) -> None:
        self._devices.pop(service_name, None)
        self._rebuild()

    # -- Internal -------------------------------------------------------

    def _rebuild(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

        if not self._devices:
            self._empty_label = QLabel("Searching for devices on your Wi-Fi network…")
            self._empty_label.setProperty("class", "muted")
            self._list_layout.addWidget(self._empty_label)
            return

        for device in sorted(self._devices.values(), key=lambda d: d.display_name):
            self._list_layout.addWidget(self._device_row(device))

    def _device_row(self, device: DiscoveredDevice) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        name = QLabel(f"📱 {device.display_name}")
        detail = QLabel(f"{device.address}  •  Not paired")
        detail.setProperty("class", "muted")
        text.addWidget(name)
        text.addWidget(detail)
        layout.addLayout(text, stretch=1)

        pair_btn = QPushButton("Pair…")
        pair_btn.setProperty("class", "primary")
        pair_btn.setEnabled(False)
        pair_btn.setToolTip("Pairing arrives in an upcoming build")
        layout.addWidget(pair_btn)
        return row
