"""Main application window: sidebar navigation + stacked pages."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.models.device import DiscoveredDevice
from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.database.db import DeviceStore
from infrastructure.discovery.service import DiscoveryService
from infrastructure.networking.receiver import ReceiverServer
from ui.pages.about_page import AboutPage
from ui.pages.dashboard_page import DashboardPage
from ui.pages.devices_page import DevicesPage
from ui.pages.history_page import HistoryPage
from ui.pages.settings_page import SettingsPage


class MainWindow(QMainWindow):
    def __init__(
        self,
        app_version: str,
        settings: SettingsStore | None = None,
        discovery: DiscoveryService | None = None,
        receiver: ReceiverServer | None = None,
        device_store: DeviceStore | None = None,
    ) -> None:
        super().__init__()
        self._discovery = discovery
        self._network_devices: set[str] = set()
        self.setWindowTitle("PhotoSync")
        self.setMinimumSize(QSize(960, 640))

        root = QWidget(objectName="appRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._pages = QStackedWidget()
        sidebar = self._build_sidebar()

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(root)

        self.dashboard = DashboardPage(settings)
        self.devices_page = DevicesPage(receiver=receiver, device_store=device_store)
        self._add_page("Dashboard", self.dashboard)
        self._add_page("Devices", self.devices_page)
        self._add_page("Backup History", HistoryPage())
        self._add_page("Settings", SettingsPage(settings))
        self._add_page("About", AboutPage(app_version))

        first = self._nav_group.buttons()[0]
        first.setChecked(True)

        if discovery is not None:
            discovery.announcing_changed.connect(self.dashboard.on_announcing_changed)
            discovery.device_found.connect(self._on_device_found)
            discovery.device_lost.connect(self._on_device_lost)

    # -- Discovery ------------------------------------------------------

    def _on_device_found(self, device: DiscoveredDevice) -> None:
        self._network_devices.add(device.service_name)
        self.devices_page.on_device_found(device)
        self.dashboard.on_network_count_changed(len(self._network_devices))

    def _on_device_lost(self, service_name: str) -> None:
        self._network_devices.discard(service_name)
        self.devices_page.on_device_lost(service_name)
        self.dashboard.on_network_count_changed(len(self._network_devices))

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget(objectName="sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(4)

        brand = QLabel("PhotoSync")
        brand.setProperty("class", "pageTitle")
        layout.addWidget(brand)
        layout.addSpacing(20)

        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_group.idClicked.connect(self._pages.setCurrentIndex)

        layout.addStretch(1)
        return sidebar

    def _add_page(self, title: str, page: QWidget) -> None:
        index = self._pages.addWidget(page)

        button = QPushButton(title)
        button.setProperty("class", "navItem")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._nav_group.addButton(button, index)

        sidebar_layout = self.centralWidget().findChild(QWidget, "sidebar").layout()
        # insert above the trailing stretch
        sidebar_layout.insertWidget(sidebar_layout.count() - 1, button)
