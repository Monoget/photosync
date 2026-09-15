"""Phase 3 unit tests: service-info parsing and UI wiring (no network)."""
import os
import socket

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from zeroconf import ServiceInfo  # noqa: E402

from core.models.device import DiscoveredDevice  # noqa: E402
from core.protocol.constants import SERVICE_TYPE_MOBILE  # noqa: E402
from infrastructure.discovery.service import device_from_service_info  # noqa: E402
from ui.windows.main_window import MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def make_info(name="Pixel 9", ip="192.168.1.23", port=40404, props=None):
    if props is None:
        props = {"protocol": "1", "name": name, "platform": "android"}
    return ServiceInfo(
        SERVICE_TYPE_MOBILE,
        f"{name}.{SERVICE_TYPE_MOBILE}",
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties=props,
    )


def test_device_from_service_info():
    device = device_from_service_info(make_info())
    assert device == DiscoveredDevice(
        service_name=f"Pixel 9.{SERVICE_TYPE_MOBILE}",
        display_name="Pixel 9",
        address="192.168.1.23",
        port=40404,
        platform="android",
        protocol_version=1,
    )


def test_device_without_props_still_parses():
    device = device_from_service_info(make_info(props={}))
    assert device is not None
    assert device.display_name == "Pixel 9"
    assert device.protocol_version is None
    assert device.platform == "unknown"


def test_main_window_tracks_found_and_lost_devices(qapp):
    window = MainWindow(app_version="test")
    device = device_from_service_info(make_info())

    window._on_device_found(device)
    assert "1 device on your network" in window.dashboard.network_status.text()
    assert device.service_name in window.devices_page._devices

    window._on_device_lost(device.service_name)
    assert "Searching" in window.dashboard.network_status.text()
    assert not window.devices_page._devices
