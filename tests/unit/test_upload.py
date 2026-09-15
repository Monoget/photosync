"""Phase 5 tests: filename organization and the upload endpoint."""
import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from infrastructure.configuration.settings_store import SettingsStore  # noqa: E402
from infrastructure.database.db import DeviceStore, PhotoStore, migrate  # noqa: E402
from infrastructure.networking.receiver import ReceiverServer  # noqa: E402
from infrastructure.security.identity import DeviceIdentity  # noqa: E402
from infrastructure.storage.organizer import (  # noqa: E402
    dest_path_for,
    sanitize_filename,
)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# -- Organizer ---------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("IMG_001.jpg", "IMG_001.jpg"),
        ("..\\..\\evil.exe", "evil.exe"),
        ("../../etc/passwd", "passwd"),
        ("bad<name>?.jpg", "bad_name__.jpg"),
        ("...", "photo.jpg"),
        ("", "photo.jpg"),
    ],
)
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_dest_path_year_month_and_uniquify(tmp_path):
    taken = datetime(2026, 9, 15, tzinfo=timezone.utc)
    first = dest_path_for(tmp_path, "IMG.jpg", taken)
    assert first == tmp_path / "2026" / "09" / "IMG.jpg"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"x")
    second = dest_path_for(tmp_path, "IMG.jpg", taken)
    assert second == tmp_path / "2026" / "09" / "IMG (1).jpg"


# -- Upload endpoint ---------------------------------------------------


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
        identity=identity,
        device_store=devices,
        pc_id="pc-1",
        app_version="test",
        photo_store=photos,
        settings=settings,
    )
    srv.start()
    code = srv.pairing.begin_session()
    token = srv.pairing.try_pair("phone-1", "Pixel", "android", code)
    yield srv, photos, dest, token
    srv.stop()


def _upload(port, token, payload: bytes, media_id="m1", filename="IMG_1.jpg",
             sha=None, taken_ms=1789500000000):
    sha = sha or hashlib.sha256(payload).hexdigest()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}/api/v1/upload", method="POST", data=payload
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-PhotoSync-Media-Id", media_id)
    req.add_header("X-PhotoSync-Filename", urllib.parse.quote(filename))
    req.add_header("X-PhotoSync-Sha256", sha)
    req.add_header("X-PhotoSync-Date-Taken", str(taken_ms))
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_upload_success_and_duplicate(server):
    srv, photos, dest, token = server
    payload = b"fake-jpeg-bytes" * 1000

    status, body = _upload(srv.port, token, payload)
    assert status == 200 and body["ok"] and not body["duplicate"]

    taken = datetime.fromtimestamp(1789500000, tz=timezone.utc)
    saved = dest / f"{taken.year:04d}" / f"{taken.month:02d}" / "IMG_1.jpg"
    assert saved.read_bytes() == payload
    assert photos.completed_count() == 1
    assert not list((dest / ".photosync-tmp").glob("*.part"))

    # same media id again -> duplicate, no new file
    status, body = _upload(srv.port, token, payload)
    assert status == 200 and body["duplicate"]
    assert photos.completed_count() == 1
    assert len(list(saved.parent.iterdir())) == 1


def test_upload_hash_mismatch_rejected(server):
    srv, photos, dest, token = server
    status, body = _upload(
        srv.port, token, b"data", media_id="m2", sha="0" * 64
    )
    assert status == 400
    assert photos.completed_count() == 0
    assert not list(dest.rglob("*.jpg"))
    assert not list((dest / ".photosync-tmp").glob("*.part"))


def test_upload_requires_auth(server):
    srv, *_ = server
    status, _ = _upload(srv.port, "bogus-token", b"data", media_id="m3")
    assert status == 401


def test_upload_path_traversal_neutralized(server):
    srv, photos, dest, token = server
    payload = b"traversal"
    status, body = _upload(
        srv.port, token, payload, media_id="m4",
        filename="..\\..\\evil.exe",
    )
    assert status == 200
    row = photos.recent(1)[0]
    saved = Path(row["destination_path"])
    assert saved.name == "evil.exe"
    assert dest in saved.parents  # never escapes the destination root
