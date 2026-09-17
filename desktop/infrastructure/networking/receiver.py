"""HTTPS receiver server: pairing, ping, and photo upload (Phases 4-5).

TLS uses this PC's persistent self-signed identity; phones pin the
certificate fingerprint at pairing time. Only private/loopback source
addresses are served — this is a LAN-only service by design (spec §12).

Uploads stream to a temporary ``.part`` file, are verified against the
client's SHA-256 before an atomic rename into ``<dest>/YYYY/MM/`` (spec
§15-16), and are only then recorded as completed.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import shutil
import socket
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import ssl

from PySide6.QtCore import QObject, Signal

from core.protocol.constants import PROTOCOL_VERSION
from infrastructure.configuration.settings_store import SettingsStore
from infrastructure.database.db import DeviceStore, PhotoStore
from infrastructure.security.identity import DeviceIdentity
from infrastructure.storage.organizer import dest_path_for, sanitize_filename

log = logging.getLogger(__name__)

MAX_BODY_BYTES = 64 * 1024
MAX_PAIR_ATTEMPTS = 5
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB per file
UPLOAD_CHUNK = 256 * 1024
DISK_RESERVE_BYTES = 200 * 1024 * 1024  # never fill the drive completely
STALE_PART_AGE_S = 7 * 24 * 3600


def part_path(tmp_dir: Path, device_id: str, media_id: str) -> Path:
    """Deterministic .part name so an interrupted transfer can resume."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", f"{device_id[:24]}_{media_id[:32]}")
    return tmp_dir / f"{safe}.part"


def clean_stale_parts(tmp_dir: Path, max_age_s: float = STALE_PART_AGE_S) -> None:
    """Delete abandoned .part files (spec §15 partial-file hygiene)."""
    if not tmp_dir.is_dir():
        return
    cutoff = time.time() - max_age_s
    for part in tmp_dir.glob("*.part"):
        try:
            if part.stat().st_mtime < cutoff:
                part.unlink()
                log.info("Removed stale partial file %s", part.name)
        except OSError:
            continue


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


class TransferEvents(QObject):
    """UI notifications for received photos (emitted from worker threads)."""

    photo_received = Signal(str)  # filename


class _Handler(BaseHTTPRequestHandler):
    server_version = "PixSynq"
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
        elif self.path.startswith("/api/v1/upload/offset"):
            self._handle_offset_query()
        else:
            self._send_json(404, {"error": "not found"})

    def _handle_offset_query(self) -> None:
        """How many bytes of this media id's .part file are already here?"""
        srv = self.server
        device = self._bearer_device()
        if device is None:
            self._send_json(401, {"error": "unauthorized"})
            return
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        media_id = (query.get("media_id") or [""])[0].strip()[:64]
        if not media_id:
            self._send_json(400, {"error": "media_id required"})
            return
        device_id = device["device_id"]
        if srv.photo_store is not None and srv.photo_store.completed_exists(  # type: ignore[attr-defined]
            device_id, media_id
        ):
            self._send_json(200, {"complete": True, "offset": 0})
            return
        settings = srv.settings  # type: ignore[attr-defined]
        dest_root = settings.destination_dir if settings else None
        offset = 0
        if dest_root is not None:
            part = part_path(Path(dest_root) / ".pixsynq-tmp", device_id, media_id)
            if part.exists():
                offset = part.stat().st_size
        self._send_json(200, {"complete": False, "offset": offset})

    def do_POST(self) -> None:  # noqa: N802
        if self._reject_non_local():
            return
        if self.path == "/api/v1/upload":
            self._handle_upload()
            return
        if self.path == "/api/v1/sync/check":
            self._handle_sync_check()
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

    # -- Sync -----------------------------------------------------------

    def _handle_sync_check(self) -> None:
        """Which of the phone's media ids still need transferring?"""
        srv = self.server
        device = self._bearer_device()
        if device is None:
            self._send_json(401, {"error": "unauthorized"})
            return
        if srv.photo_store is None:  # type: ignore[attr-defined]
            self._send_json(409, {"error": "not ready"})
            return
        body = self._read_json()
        if body is None or not isinstance(body.get("media_ids"), list):
            self._send_json(400, {"error": "invalid request"})
            return
        media_ids = [str(m)[:64] for m in body["media_ids"][:1000]]
        needed = srv.photo_store.filter_needed(  # type: ignore[attr-defined]
            device["device_id"], media_ids
        )
        srv.device_store.touch_last_seen(device["device_id"])  # type: ignore[attr-defined]
        self._send_json(200, {"needed": needed})

    # -- Upload ---------------------------------------------------------

    def _discard_body(self, length: int) -> None:
        remaining = length
        while remaining > 0:
            chunk = self.rfile.read(min(UPLOAD_CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _handle_upload(self) -> None:
        srv = self.server
        device = self._bearer_device()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        def fail(status: int, error: str, discard: bool = True) -> None:
            if discard:
                self._discard_body(length)
            self._send_json(status, {"error": error})

        if device is None:
            return fail(401, "unauthorized")
        if getattr(srv, "paused", False):
            return fail(503, "backup is paused on the PC")
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            return fail(400, "invalid content length", discard=False)

        settings = srv.settings  # type: ignore[attr-defined]
        dest_root = settings.destination_dir if settings else None
        if dest_root is None or srv.photo_store is None:  # type: ignore[attr-defined]
            return fail(409, "no destination folder configured")

        media_id = self.headers.get("X-PixSynq-Media-Id", "").strip()[:64]
        raw_name = self.headers.get("X-PixSynq-Filename", "")
        filename = sanitize_filename(urllib.parse.unquote(raw_name))
        expected_hash = self.headers.get("X-PixSynq-Sha256", "").strip().lower()
        if not media_id or len(expected_hash) != 64:
            return fail(400, "missing media id or sha256")

        taken_at = None
        taken_raw = self.headers.get("X-PixSynq-Date-Taken", "")
        try:
            taken_at = datetime.fromtimestamp(int(taken_raw) / 1000, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass

        device_id = device["device_id"]
        if srv.photo_store.completed_exists(device_id, media_id):  # type: ignore[attr-defined]
            self._discard_body(length)
            self._send_json(200, {"ok": True, "duplicate": True})
            return

        # Same bytes under a new MediaStore id (re-index, restored backup…):
        # record the alias without writing a second copy (spec §14).
        same = srv.photo_store.find_by_hash(  # type: ignore[attr-defined]
            device_id, expected_hash, length
        )
        if same is not None:
            self._discard_body(length)
            srv.photo_store.record_completed(  # type: ignore[attr-defined]
                device_id=device_id,
                media_id=media_id,
                filename=same["filename"],
                file_size=length,
                date_taken=same["date_taken"],
                content_hash=expected_hash,
                destination_path=same["destination_path"],
            )
            self._send_json(200, {"ok": True, "duplicate": True})
            return

        # Resume support (spec §15): this request carries `length` bytes of
        # a `total`-byte file starting at `offset`. A deterministic .part
        # name lets an interrupted transfer continue where it stopped.
        try:
            total = int(self.headers.get("X-PixSynq-Total-Size", str(length)))
            offset = int(self.headers.get("X-PixSynq-Offset", "0"))
        except ValueError:
            return fail(400, "invalid resume headers")
        if total <= 0 or total > MAX_UPLOAD_BYTES or offset < 0 \
                or offset + length > total:
            return fail(400, "inconsistent resume headers")

        try:
            free = shutil.disk_usage(dest_root).free
        except OSError as exc:
            return fail(500, f"destination unavailable: {exc.strerror or exc}")
        if free < total + DISK_RESERVE_BYTES:
            return fail(507, "insufficient disk space on the backup drive")

        tmp_dir = Path(dest_root) / ".pixsynq-tmp"
        try:
            tmp_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return fail(500, f"destination unavailable: {exc.strerror or exc}")

        part = part_path(tmp_dir, device_id, media_id)
        current = part.stat().st_size if part.exists() else 0
        if offset != current and offset != 0:
            return fail(409, f"offset mismatch, have {current}")

        received = 0
        try:
            with open(part, "wb" if offset == 0 else "ab") as out:
                while received < length:
                    chunk = self.rfile.read(min(UPLOAD_CHUNK, length - received))
                    if not chunk:
                        break
                    out.write(chunk)
                    received += len(chunk)

            if received != length:
                # Connection broke mid-transfer: keep the .part so the
                # phone can resume from the current offset (spec §15).
                log.warning(
                    "Interrupted upload of %s at %d/%d bytes",
                    filename, offset + received, total,
                )
                return

            if offset + length < total:
                self._send_json(
                    200, {"ok": True, "partial": True, "received": offset + length}
                )
                return

            # Whole file present — verify before it ever becomes visible.
            digest = hashlib.sha256()
            with open(part, "rb") as done:
                for chunk in iter(lambda: done.read(UPLOAD_CHUNK), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_hash:
                part.unlink(missing_ok=True)
                self._send_json(400, {"error": "hash mismatch"})
                return

            final = dest_path_for(Path(dest_root), filename, taken_at)
            final.parent.mkdir(parents=True, exist_ok=True)
            part.replace(final)
        except OSError as exc:
            log.exception("Upload failed for %s", filename)
            self._send_json(500, {"error": f"write failed: {exc.strerror or exc}"})
            return

        srv.photo_store.record_completed(  # type: ignore[attr-defined]
            device_id=device_id,
            media_id=media_id,
            filename=final.name,
            file_size=total,
            date_taken=taken_at.isoformat() if taken_at else None,
            content_hash=expected_hash,
            destination_path=str(final),
        )
        srv.device_store.touch_last_seen(device_id)  # type: ignore[attr-defined]
        srv.transfer_events.photo_received.emit(final.name)  # type: ignore[attr-defined]
        log.info("Received %s (%d bytes) from %s", final.name, total, device["name"])
        self._send_json(200, {"ok": True, "duplicate": False})

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
        photo_store: PhotoStore | None = None,
        settings: SettingsStore | None = None,
    ) -> None:
        self._identity = identity
        self.pairing = PairingManager(device_store)
        self.transfer_events = TransferEvents()
        self._httpd = ThreadingHTTPServer(("", 0), _Handler)
        self._httpd.daemon_threads = True
        # attributes the handler reads
        self._httpd.device_store = device_store  # type: ignore[attr-defined]
        self._httpd.photo_store = photo_store  # type: ignore[attr-defined]
        self._httpd.settings = settings  # type: ignore[attr-defined]
        self._httpd.pairing = self.pairing  # type: ignore[attr-defined]
        self._httpd.transfer_events = self.transfer_events  # type: ignore[attr-defined]
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

    def set_paused(self, paused: bool) -> None:
        self._httpd.paused = paused  # type: ignore[attr-defined]
        log.info("Backup receiving %s", "paused" if paused else "resumed")

    @property
    def paused(self) -> bool:
        return bool(getattr(self._httpd, "paused", False))

    def start(self) -> None:
        settings = getattr(self._httpd, "settings", None)
        dest = settings.destination_dir if settings else None
        if dest is not None:
            clean_stale_parts(Path(dest) / ".pixsynq-tmp")
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True, name="receiver"
        )
        self._thread.start()
        log.info("Receiver listening on port %s (TLS)", self.port)

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
