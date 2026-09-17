"""Phase 7 tests: resumable uploads, offset queries, stale-part cleanup."""
import hashlib
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from infrastructure.configuration.settings_store import SettingsStore  # noqa: E402
from infrastructure.database.db import DeviceStore, PhotoStore, migrate  # noqa: E402
from infrastructure.networking.receiver import (  # noqa: E402
    ReceiverServer,
    clean_stale_parts,
    part_path,
)
from infrastructure.security.identity import DeviceIdentity  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def server(qapp, tmp_path):
    db = tmp_path / "pixsynq.db"
    migrate(db)
    devices = DeviceStore(db)
    photos = PhotoStore(db)
    settings = SettingsStore(tmp_path / "settings.json")
    dest = tmp_path / "dest"
    dest.mkdir()
    settings.set_destination_dir(dest)
    identity = DeviceIdentity.load_or_create(tmp_path)
    srv = ReceiverServer(
        identity=identity, device_store=devices, pc_id="pc-1",
        app_version="test", photo_store=photos, settings=settings,
    )
    srv.start()
    code = srv.pairing.begin_session()
    token = srv.pairing.try_pair("phone-1", "Pixel", "android", code)
    yield srv, photos, dest, token
    srv.stop()


CTX = ssl._create_unverified_context()


def _chunk(port, token, chunk: bytes, media_id, total, offset, sha,
           filename="IMG_R.jpg"):
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/v1/upload", method="POST", data=chunk
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-PixSynq-Media-Id", media_id)
    req.add_header("X-PixSynq-Filename", urllib.parse.quote(filename))
    req.add_header("X-PixSynq-Sha256", sha)
    req.add_header("X-PixSynq-Date-Taken", "1789500000000")
    req.add_header("X-PixSynq-Total-Size", str(total))
    req.add_header("X-PixSynq-Offset", str(offset))
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def _offset(port, token, media_id):
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/v1/upload/offset?media_id={media_id}"
    )
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, context=CTX, timeout=15) as resp:
        return json.loads(resp.read())


def test_resume_in_two_chunks(server):
    srv, photos, dest, token = server
    payload = os.urandom(4000)
    sha = hashlib.sha256(payload).hexdigest()

    status, body = _chunk(srv.port, token, payload[:1500], "r1", 4000, 0, sha)
    assert status == 200 and body["partial"] and body["received"] == 1500

    assert _offset(srv.port, token, "r1") == {"complete": False, "offset": 1500}

    status, body = _chunk(srv.port, token, payload[1500:], "r1", 4000, 1500, sha)
    assert status == 200 and not body.get("partial") and not body["duplicate"]

    saved = next(p for p in dest.rglob("*.jpg"))
    assert saved.read_bytes() == payload
    assert photos.completed_exists("phone-1", "r1")
    assert _offset(srv.port, token, "r1")["complete"] is True


def test_offset_mismatch_rejected(server):
    srv, _, _, token = server
    payload = os.urandom(1000)
    sha = hashlib.sha256(payload).hexdigest()
    _chunk(srv.port, token, payload[:400], "r2", 1000, 0, sha)
    status, body = _chunk(srv.port, token, payload[500:], "r2", 1000, 500, sha)
    assert status == 409
    assert "offset mismatch" in body["error"]


def test_hash_mismatch_after_resume_discards_part(server):
    srv, photos, dest, token = server
    payload = os.urandom(2000)
    _chunk(srv.port, token, payload[:1000], "r3", 2000, 0, "f" * 64)
    status, body = _chunk(srv.port, token, payload[1000:], "r3", 2000, 1000, "f" * 64)
    assert status == 400 and body["error"] == "hash mismatch"
    assert not list((dest / ".pixsynq-tmp").glob("*.part"))
    assert not photos.completed_exists("phone-1", "r3")


def test_paused_receiver_rejects_uploads(server):
    srv, _, _, token = server
    srv.set_paused(True)
    payload = b"x" * 100
    status, body = _chunk(
        srv.port, token, payload, "r4", 100, 0,
        hashlib.sha256(payload).hexdigest(),
    )
    assert status == 503
    srv.set_paused(False)
    status, _ = _chunk(
        srv.port, token, payload, "r4", 100, 0,
        hashlib.sha256(payload).hexdigest(),
    )
    assert status == 200


def test_clean_stale_parts(tmp_path):
    tmp = tmp_path / ".pixsynq-tmp"
    tmp.mkdir()
    old = tmp / "old.part"
    fresh = tmp / "fresh.part"
    old.write_bytes(b"o")
    fresh.write_bytes(b"f")
    ancient = time.time() - 8 * 24 * 3600
    os.utime(old, (ancient, ancient))
    clean_stale_parts(tmp)
    assert not old.exists()
    assert fresh.exists()


def test_part_path_is_safe_and_deterministic(tmp_path):
    a = part_path(tmp_path, "dev/../1", "m:1")
    b = part_path(tmp_path, "dev/../1", "m:1")
    assert a == b
    assert a.parent == tmp_path
    assert a.suffix == ".part"
