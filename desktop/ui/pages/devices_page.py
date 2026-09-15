"""Devices page: network devices, pairing entry point, and paired devices."""
from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.models.device import DiscoveredDevice
from infrastructure.database.db import DeviceStore
from infrastructure.networking.receiver import ReceiverServer
from ui.pages.base_page import BasePage
from ui.widgets.card import Card


class DevicesPage(BasePage):
    def __init__(
        self,
        receiver: ReceiverServer | None = None,
        device_store: DeviceStore | None = None,
    ) -> None:
        super().__init__("Devices")
        self._receiver = receiver
        self._store = device_store
        self._devices: dict[str, DiscoveredDevice] = {}

        network_card = Card("On Your Network")
        self._list_host = QWidget()
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(8)
        network_card.add(self._list_host)
        self.body.addWidget(network_card)

        paired_card = Card("Paired Devices")
        self._paired_host = QWidget()
        self._paired_layout = QVBoxLayout(self._paired_host)
        self._paired_layout.setContentsMargins(0, 0, 0, 0)
        self._paired_layout.setSpacing(8)
        paired_card.add(self._paired_host)

        pair_btn = QPushButton("Pair a Device…")
        pair_btn.setProperty("class", "primary")
        pair_btn.setEnabled(receiver is not None)
        pair_btn.clicked.connect(self._open_pair_dialog)
        paired_card.add(pair_btn)
        self.body.addWidget(paired_card)

        if receiver is not None:
            receiver.pairing.device_paired.connect(lambda _n: self._rebuild_paired())

        self._rebuild_network()
        self._rebuild_paired()
        self.finish()

    # -- Slots (connected to DiscoveryService) --------------------------

    def on_device_found(self, device: DiscoveredDevice) -> None:
        self._devices[device.service_name] = device
        self._rebuild_network()

    def on_device_lost(self, service_name: str) -> None:
        self._devices.pop(service_name, None)
        self._rebuild_network()

    # -- Internal -------------------------------------------------------

    def _paired_names(self) -> set[str]:
        if self._store is None:
            return set()
        return {row["name"] for row in self._store.trusted_devices()}

    def _open_pair_dialog(self) -> None:
        from ui.dialogs.pair_dialog import PairDialog

        assert self._receiver is not None
        PairDialog(self._receiver, self).exec()
        self._rebuild_paired()

    @staticmethod
    def _clear(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _rebuild_network(self) -> None:
        self._clear(self._list_layout)
        if not self._devices:
            empty = QLabel("Searching for devices on your Wi-Fi network…")
            empty.setProperty("class", "muted")
            self._list_layout.addWidget(empty)
            return
        paired = self._paired_names()
        for device in sorted(self._devices.values(), key=lambda d: d.display_name):
            self._list_layout.addWidget(
                self._network_row(device, device.display_name in paired)
            )

    def _network_row(self, device: DiscoveredDevice, is_paired: bool) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        name = QLabel(f"📱 {device.display_name}")
        status = "Paired" if is_paired else "Not paired"
        detail = QLabel(f"{device.address}  •  {status}")
        detail.setProperty("class", "muted")
        text.addWidget(name)
        text.addWidget(detail)
        layout.addLayout(text, stretch=1)

        if not is_paired and self._receiver is not None:
            pair_btn = QPushButton("Pair…")
            pair_btn.setProperty("class", "primary")
            pair_btn.clicked.connect(self._open_pair_dialog)
            layout.addWidget(pair_btn)
        return row

    def _rebuild_paired(self) -> None:
        self._clear(self._paired_layout)
        rows = self._store.trusted_devices() if self._store else []
        if not rows:
            empty = QLabel("No devices paired")
            self._paired_layout.addWidget(empty)
            return
        for row in rows:
            widget = QWidget()
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            name = QLabel(f"📱 {row['name']}")
            paired_date = (row["paired_at"] or "")[:10]
            detail = QLabel(f"{row['platform']}  •  Paired {paired_date}")
            detail.setProperty("class", "muted")
            layout.addWidget(name)
            layout.addWidget(detail)
            self._paired_layout.addWidget(widget)
        self._rebuild_network()  # refresh paired badges
