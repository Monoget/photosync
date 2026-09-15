"""Phase 3 integration test: real mDNS announce + browse on this machine.

Registers a fake phone service with an independent Zeroconf instance and
asserts DiscoveryService both announces itself and discovers the phone.
"""
import os
import socket
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from zeroconf import ServiceInfo, Zeroconf  # noqa: E402

from core.protocol.constants import SERVICE_TYPE_MOBILE  # noqa: E402
from infrastructure.discovery.service import DiscoveryService, local_ip  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def pump_until(condition, timeout_s=12.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_announce_and_discover_phone(qapp):
    found: list = []
    announced: list = []

    service = DiscoveryService(app_version="test")
    service.device_found.connect(found.append)
    service.announcing_changed.connect(announced.append)
    service.start(port=45001)

    assert pump_until(lambda: announced), "announcement never started"
    assert announced[-1] is True

    phone_zc = Zeroconf()
    phone_info = ServiceInfo(
        SERVICE_TYPE_MOBILE,
        f"TestPhone.{SERVICE_TYPE_MOBILE}",
        addresses=[socket.inet_aton(local_ip())],
        port=45454,
        properties={"protocol": "1", "name": "Test Phone", "platform": "android"},
    )
    try:
        phone_zc.register_service(phone_info)
        assert pump_until(lambda: found), "phone service was never discovered"
        device = found[0]
        assert device.display_name == "Test Phone"
        assert device.port == 45454
        assert device.protocol_version == 1
    finally:
        phone_zc.unregister_service(phone_info)
        phone_zc.close()
        service.stop()
