"""HTTPS receiver server: pairing and authenticated ping (Phase 4).

The transfer endpoints land here in Phase 5. TLS uses this PC's
persistent self-signed identity; phones pin the certificate fingerprint
at pairing time. Only private/loopback source addresses are served —
this is a LAN-only service by design (spec §12).
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ssl

from PySide6.QtCore import QObject, Signal

from core.protocol.constants import PROTOCOL_VERSION
from infrastructure.database.db import DeviceStore
from infrastructure.security.identity import DeviceIdentity

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
MAX_PAIR_ATTEMPTS = 5


def is_local_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PairingManager(QObject):
    """Holds the active pairing session; emits UI events."""

    device_paired = Signal(str)  # device name
    attempt_failed = Signal(int)  # attempts remaining

    def __init__(self, device_store: DeviceStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._store = device_store
        self._lock = threading.Lock()
        self._code: str | None = None
        self._attempts_left = 0

    def begin_session(self) -> str:
        with self._lock:
            self._code = f"{secrets.randbelow(1_000_000):06d}"
            self._attempts_left = MAX_PAIR_ATTEMPTS
            return self._code

    def end_session(self) -> None:
        with self._lock:
            self._code = None
            self._attempts_left = 0

    def try_pair(
        self, device_id: str, name: str, platform: str, code: str
    ) -> str | None:
        """Return a fresh auth token on success, None on failure."""
        with self._lock:
            if self._code is None or self._attempts_left <= 0:
                return None
            if not hmac.compare_digest(code, self._code):
                self._attempts_left -= 1
                if self._attempts_left <= 0:
                    self._code = None
                self.attempt_failed.emit(self._attempts_left)
                return None
            # success — single use
            self._code = None
            self._attempts_left = 0

        token = secrets.token_hex(32)
        self._store.upsert_device(device_id, name, platform, hash_token(token))
        log.info("Paired device %s (%s)", name, device_id)
        self.device_paired.emit(name)
        return token


class _Handler(BaseHTTPRequestHandler):
    server_version = "PhotoSync"
    protocol_version = "HTTP/1.1"

    # -- Helpers --------------------------------------------------------

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > MAX_BODY_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _reject_non_local(self) -> bool:
        if is_local_address(self.client_address[0]):
            return False
        self._send_json(403, {"error": "local network only"})
        return True

    def _bearer_device(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        return self.server.device_store.find_by_token_hash(  # type: ignore[attr-defined]
            hash_token(auth.removeprefix("Bearer ").strip())
        )

    # -- Routes ---------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        srv = self.server
        if self.path == "/api/v1/info":
            self._send_json(
                200,
                {
                    "name": socket.gethostname(),
                    "platform": "windows",
                    "protocol": PROTOCOL_VERSION,
                    "app_version": srv.app_version,  # type: ignore[attr-defined]
                    "pc_id": srv.pc_id,  # type: ignore[attr-defined]
                },
            )
        elif self.path == "/api/v1/ping":
            device = self._bearer_device()
            if device is None:
                self._send_json(401, {"error": "unauthorized"})
                return
            srv.device_store.touch_last_seen(device["device_id"])  # type: ignore[attr-defined]
            self._send_json(200, {"ok": True, "name": socket.gethostname()})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        if self.path != "/api/v1/pair":
            self._send_json(404, {"error": "not found"})
            return
        body = self._read_json()
        if body is None:
            self._send_json(400, {"error": "invalid request"})
            return
        device_id = str(body.get("device_id", ""))[:64]
        name = str(body.get("name", ""))[:100]
        platform = str(body.get("platform", ""))[:32]
        code = str(body.get("code", ""))[:16]
        if not device_id or not name or not code:
            self._send_json(400, {"error": "missing fields"})
            return
        token = self.server.pairing.try_pair(  # type: ignore[attr-defined]
            device_id, name, platform or "unknown", code
        )
        if token is None:
            self._send_json(403, {"error": "invalid or expired pairing code"})
            return
        self._send_json(
            200,
            {
                "token": token,
                "pc_id": self.server.pc_id,  # type: ignore[attr-defined]
                "pc_name": socket.gethostname(),
                "protocol": PROTOCOL_VERSION,
            },
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        log.debug("receiver %s %s", self.client_address[0], format % args)


class ReceiverServer:
    """Owns the HTTPS server socket; its port is what discovery advertises."""

    def __init__(
        self,
        identity: DeviceIdentity,
        device_store: DeviceStore,
        pc_id: str,
        app_version: str,
    ) -> None:
        self._identity = identity
        self.pairing = PairingManager(device_store)
        self._httpd = ThreadingHTTPServer(("", 0), _Handler)
        self._httpd.daemon_threads = True
        # attributes the handler reads
        self._httpd.device_store = device_store  # type: ignore[attr-defined]
        self._httpd.pairing = self.pairing  # type: ignore[attr-defined]
        self._httpd.pc_id = pc_id  # type: ignore[attr-defined]
        self._httpd.app_version = app_version  # type: ignore[attr-defined]

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(identity.cert_path), str(identity.key_path))
        self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    @property
    def fingerprint(self) -> str:
        return self._identity.fingerprint

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="receiver"
        )
        self._thread.start()
        log.info("Receiver listening on port %s (TLS)", self.port)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
