"""Phase 6 tests: sync-check endpoint and content-hash deduplication."""
import hashlib
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from infrastructure.configuration.settings_store import SettingsStore  # noqa: E402
from infrastructure.database.db import DeviceStore, PhotoStore, migrate  # noqa: E402
from infrastructure.networking.receiver import ReceiverServer  # noqa: E402
from infrastructure.security.identity import DeviceIdentity  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def server(qapp, tmp_path):
    db = tmp_path / "photosync.db"
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


def _post_json(port, path, token, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}", method="POST", data=data
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def _upload(port, token, payload, media_id, filename="IMG.jpg"):
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/v1/upload", method="POST", data=payload
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-PhotoSync-Media-Id", media_id)
    req.add_header("X-PhotoSync-Filename", urllib.parse.quote(filename))
    req.add_header("X-PhotoSync-Sha256", hashlib.sha256(payload).hexdigest())
    req.add_header("X-PhotoSync-Date-Taken", "1789500000000")
    ctx = ssl._create_unverified_context()
    with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
        return resp.status, json.loads(resp.read())


def test_sync_check_reports_only_unknown_ids(server):
    srv, photos, dest, token = server
    _upload(srv.port, token, b"a" * 100, "m1")

    status, body = _post_json(
        srv.port, "/api/v1/sync/check", token,
        {"media_ids": ["m1", "m2", "m3"]},
    )
    assert status == 200
    assert body["needed"] == ["m2", "m3"]


def test_sync_check_requires_auth(server):
    srv, *_ = server
    status, _ = _post_json(
        srv.port, "/api/v1/sync/check", "bogus", {"media_ids": ["m1"]}
    )
    assert status == 401


def test_sync_check_rejects_bad_body(server):
    srv, _, _, token = server
    status, _ = _post_json(srv.port, "/api/v1/sync/check", token, {"nope": 1})
    assert status == 400


def test_hash_dedup_records_alias_without_second_file(server):
    srv, photos, dest, token = server
    payload = b"same-bytes" * 500

    status, body = _upload(srv.port, token, payload, "m10", "IMG_A.jpg")
    assert status == 200 and not body["duplicate"]

    # Same content, new media id (e.g. MediaStore re-index)
    status, body = _upload(srv.port, token, payload, "m11", "IMG_A_copy.jpg")
    assert status == 200 and body["duplicate"]

    files = [p for p in dest.rglob("*") if p.is_file()]
    assert len(files) == 1  # no second copy on disk
    assert photos.completed_count() == 1  # distinct files
    assert photos.completed_exists("phone-1", "m11")  # alias recorded

    # both ids now report as backed up
    status, body = _post_json(
        srv.port, "/api/v1/sync/check", token, {"media_ids": ["m10", "m11"]}
    )
    assert body["needed"] == []
