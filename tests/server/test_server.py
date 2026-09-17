"""Server API tests (Flask test client)."""
import base64
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))

from app import create_app  # noqa: E402


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "server.db")
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client, tmp_path / "server.db"


REG = {
    "installation_id": "11111111-2222-3333-4444-555555555555",
    "name": "Ada",
    "email": "ada@example.com",
    "desktop_username": "ada",
    "application_version": "1.0.0",
    "operating_system": "Windows",
    "os_version": "10.0.19045",
    "architecture": "x64",
}


def test_register_and_reregister(client):
    c, db = client
    assert c.post("/api/v1/installations/register", json=REG).status_code == 200
    # re-register updates, not duplicates
    again = dict(REG, application_version="1.1.0")
    assert c.post("/api/v1/installations/register", json=again).status_code == 200
    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT * FROM installations").fetchall()
    assert len(rows) == 1


def test_register_validation(client):
    c, _ = client
    bad = dict(REG, email="not-an-email")
    assert c.post("/api/v1/installations/register", json=bad).status_code == 400
    assert c.post("/api/v1/installations/register", json={}).status_code == 400


def test_register_records_server_side_ip(client):
    c, db = client
    payload = dict(REG, ip_address="8.8.8.8")  # client-supplied IP is ignored
    c.post("/api/v1/installations/register", json=payload)
    with sqlite3.connect(db) as conn:
        ip = conn.execute("SELECT ip_address FROM installations").fetchone()[0]
    assert ip != "8.8.8.8"


def test_heartbeat(client):
    c, _ = client
    c.post("/api/v1/installations/register", json=REG)
    beat = {"installation_id": REG["installation_id"], "application_version": "1.2.0"}
    assert c.post("/api/v1/installations/heartbeat", json=beat).status_code == 200
    unknown = {"installation_id": "99999999-0000-0000-0000-000000000000"}
    assert c.post("/api/v1/installations/heartbeat", json=unknown).status_code == 404


def test_update_feed(client):
    c, db = client
    assert c.get("/api/v1/updates/latest").status_code == 404
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO releases (platform, architecture, version, mandatory,
                title, message, download_url, sha256, created_at)
            VALUES ('windows', 'x64', '1.1.0', 0, 'PixSynq 1.1.0',
                'Faster transfers', 'https://example.com/PixSynq-1.1.0.exe',
                ?, ?)
            """,
            ("a" * 64, datetime.now(timezone.utc).isoformat()),
        )
    resp = c.get("/api/v1/updates/latest?platform=windows&architecture=x64")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["version"] == "1.1.0"
    assert body["sha256"] == "a" * 64


def test_admin_requires_auth(client, monkeypatch):
    c, _ = client
    # disabled entirely without configured credentials
    monkeypatch.delenv("ADMIN_USER", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    assert c.get("/admin").status_code == 404

    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "hunter2hunter2")
    assert c.get("/admin").status_code == 401
    token = base64.b64encode(b"admin:hunter2hunter2").decode()
    resp = c.get("/admin", headers={"Authorization": f"Basic {token}"})
    assert resp.status_code == 200
    assert b"PixSynq Installations" in resp.data


def test_rate_limit(client):
    c, _ = client
    last = None
    for _ in range(40):
        last = c.post("/api/v1/installations/heartbeat", json={"installation_id": "x" * 12})
    assert last.status_code == 429
