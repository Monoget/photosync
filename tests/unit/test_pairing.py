"""Phase 4 tests: TLS identity, device store, and the pairing HTTPS flow."""
import json
import os
import ssl
import urllib.error
import urllib.request

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from infrastructure.database.db import DeviceStore, migrate  # noqa: E402
from infrastructure.networking.receiver import (  # noqa: E402
    ReceiverServer,
    hash_token,
    is_local_address,
)
from infrastructure.security.identity import DeviceIdentity  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# -- Identity ----------------------------------------------------------


def test_identity_is_persistent(tmp_path):
    first = DeviceIdentity.load_or_create(tmp_path)
    second = DeviceIdentity.load_or_create(tmp_path)
    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert first.cert_path.is_file() and first.key_path.is_file()


# -- Database ----------------------------------------------------------


def test_migrate_idempotent_and_device_roundtrip(tmp_path):
    db = tmp_path / "pixsynq.db"
    migrate(db)
    migrate(db)  # second run must be a no-op
    store = DeviceStore(db)
    store.upsert_device("dev-1", "Pixel", "android", hash_token("secret"))
    store.upsert_device("dev-1", "Pixel 9", "android", hash_token("secret2"))

    devices = store.trusted_devices()
    assert len(devices) == 1
    assert devices[0]["name"] == "Pixel 9"
    assert store.find_by_token_hash(hash_token("secret2")) is not None
    assert store.find_by_token_hash(hash_token("secret")) is None


# -- Local-address guard ----------------------------------------------


@pytest.mark.parametrize(
    "address,expected",
    [
        ("127.0.0.1", True),
        ("192.168.1.5", True),
        ("10.0.0.2", True),
        ("8.8.8.8", False),
        ("not-an-ip", False),
    ],
)
def test_is_local_address(address, expected):
    assert is_local_address(address) is expected


# -- Pairing over real TLS ---------------------------------------------


@pytest.fixture()
def receiver(qapp, tmp_path):
    db = tmp_path / "pixsynq.db"
    migrate(db)
    store = DeviceStore(db)
    identity = DeviceIdentity.load_or_create(tmp_path)
    server = ReceiverServer(
        identity=identity, device_store=store, pc_id="pc-1", app_version="test"
    )
    server.start()
    yield server, store
    server.stop()


def _request(port, path, method="GET", body=None, token=None):
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(
        f"https://127.0.0.1:{port}{path}", method=method
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data=data, context=ctx, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_info_endpoint(receiver):
    server, _ = receiver
    status, payload = _request(server.port, "/api/v1/info")
    assert status == 200
    assert payload["pc_id"] == "pc-1"
    assert payload["protocol"] == 1


def test_pair_wrong_then_right_code_then_ping(receiver):
    server, store = receiver
    code = server.pairing.begin_session()

    wrong = "000000" if code != "000000" else "111111"
    status, _ = _request(
        server.port,
        "/api/v1/pair",
        method="POST",
        body={"device_id": "d1", "name": "Pixel", "platform": "android", "code": wrong},
    )
    assert status == 403

    status, payload = _request(
        server.port,
        "/api/v1/pair",
        method="POST",
        body={"device_id": "d1", "name": "Pixel", "platform": "android", "code": code},
    )
    assert status == 200
    token = payload["token"]
    assert payload["pc_id"] == "pc-1"
    assert store.find_by_token_hash(hash_token(token)) is not None

    # code is single-use
    status, _ = _request(
        server.port,
        "/api/v1/pair",
        method="POST",
        body={"device_id": "d2", "name": "Other", "platform": "android", "code": code},
    )
    assert status == 403

    status, payload = _request(server.port, "/api/v1/ping", token=token)
    assert status == 200 and payload["ok"] is True

    status, _ = _request(server.port, "/api/v1/ping", token="bogus")
    assert status == 401


def test_pair_without_session_rejected(receiver):
    server, _ = receiver
    status, _ = _request(
        server.port,
        "/api/v1/pair",
        method="POST",
        body={"device_id": "d1", "name": "Pixel", "platform": "android", "code": "123456"},
    )
    assert status == 403


def test_pair_lockout_after_max_attempts(receiver):
    server, _ = receiver
    code = server.pairing.begin_session()
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        status, _ = _request(
            server.port,
            "/api/v1/pair",
            method="POST",
            body={"device_id": "d1", "name": "P", "platform": "android", "code": wrong},
        )
        assert status == 403
    # correct code no longer works — session invalidated
    status, _ = _request(
        server.port,
        "/api/v1/pair",
        method="POST",
        body={"device_id": "d1", "name": "P", "platform": "android", "code": code},
    )
    assert status == 403
