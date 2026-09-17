"""Local-network discovery via mDNS (zeroconf).

Two roles, both owned by :class:`DiscoveryService`:

* **Announce** — register ``_pixsynq._tcp.local.`` for this PC so phones
  can find it. The advertised port is a real bound TCP listener that the
  Phase-5 transfer receiver will take over.
* **Browse** — watch for ``_pixsynq-mobile._tcp.local.`` announcements so
  the UI can show phones on the network before pairing.

Zeroconf runs its own daemon threads; results are delivered to the GUI
thread through Qt signals (queued automatically across threads).
"""
from __future__ import annotations

import logging
import socket
import threading

from PySide6.QtCore import QObject, Signal
from zeroconf import ServiceBrowser, ServiceInfo, ServiceStateChange, Zeroconf

from core.models.device import DiscoveredDevice
from core.protocol.constants import (
    PROTOCOL_VERSION,
    SERVICE_TYPE_DESKTOP,
    SERVICE_TYPE_MOBILE,
)

log = logging.getLogger(__name__)


def local_ip() -> str:
    """Best-effort LAN IP (UDP connect sends no packets)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"


def device_from_service_info(info: ServiceInfo) -> DiscoveredDevice | None:
    """Translate zeroconf ServiceInfo into a DiscoveredDevice."""
    addresses = info.parsed_addresses()
    if not addresses or not info.port:
        return None
    props: dict[str, str] = {}
    for key, value in (info.properties or {}).items():
        try:
            props[key.decode("utf-8")] = (
                value.decode("utf-8") if isinstance(value, bytes) else str(value)
            )
        except (UnicodeDecodeError, AttributeError):
            continue
    try:
        protocol = int(props["protocol"])
    except (KeyError, ValueError):
        protocol = None
    display = props.get("name") or info.name.split(".")[0]
    return DiscoveredDevice(
        service_name=info.name,
        display_name=display,
        address=addresses[0],
        port=info.port,
        platform=props.get("platform", "unknown"),
        protocol_version=protocol,
    )


class DiscoveryService(QObject):
    announcing_changed = Signal(bool)
    device_found = Signal(object)  # DiscoveredDevice
    device_lost = Signal(str)  # service_name

    def __init__(self, app_version: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._app_version = app_version
        self._zeroconf: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None
        self._service_info: ServiceInfo | None = None

    # -- Lifecycle ------------------------------------------------------

    def start(self, port: int) -> None:
        """Announce the given receiver port + browse, off the GUI thread."""
        threading.Thread(
            target=self._start_blocking, args=(port,), daemon=True
        ).start()

    def _start_blocking(self, port: int) -> None:
        try:
            hostname = socket.gethostname()
            ip = local_ip()
            self._service_info = ServiceInfo(
                SERVICE_TYPE_DESKTOP,
                f"{hostname}.{SERVICE_TYPE_DESKTOP}",
                addresses=[socket.inet_aton(ip)],
                port=port,
                properties={
                    "protocol": str(PROTOCOL_VERSION),
                    "name": hostname,
                    "platform": "windows",
                    "app_version": self._app_version,
                },
            )
            self._zeroconf = Zeroconf()
            self._zeroconf.register_service(self._service_info)
            log.info("Announcing %s at %s:%s", hostname, ip, port)
            self.announcing_changed.emit(True)

            self._browser = ServiceBrowser(
                self._zeroconf,
                SERVICE_TYPE_MOBILE,
                handlers=[self._on_service_state_change],
            )
        except OSError:
            log.exception("Discovery failed to start")
            self.announcing_changed.emit(False)

    def stop(self) -> None:
        zc, self._zeroconf = self._zeroconf, None
        if zc is not None:
            try:
                if self._service_info is not None:
                    zc.unregister_service(self._service_info)
                zc.close()
            except OSError:
                log.exception("Error stopping discovery")
        self.announcing_changed.emit(False)

    # -- Browsing (called on zeroconf threads) --------------------------

    def _on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is ServiceStateChange.Removed:
            log.info("Device left the network: %s", name)
            self.device_lost.emit(name)
            return
        info = zeroconf.get_service_info(service_type, name, timeout=3000)
        if info is None:
            return
        device = device_from_service_info(info)
        if device is not None:
            log.info(
                "Device on network: %s (%s:%s)",
                device.display_name,
                device.address,
                device.port,
            )
            self.device_found.emit(device)
