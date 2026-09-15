"""SQLite database with simple PRAGMA user_version migrations (spec §21).

Connections are opened per operation so any thread (GUI, receiver
workers) can use the store safely.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

MIGRATIONS: list[str] = [
    # v1 — initial schema
    """
    CREATE TABLE devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        platform TEXT NOT NULL,
        token_hash TEXT NOT NULL,
        paired_at TEXT NOT NULL,
        last_seen TEXT,
        is_trusted INTEGER NOT NULL DEFAULT 1
    );
    CREATE TABLE photos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        file_size INTEGER,
        date_taken TEXT,
        content_hash TEXT,
        destination_path TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        completed_at TEXT,
        UNIQUE (device_id, media_id)
    );
    CREATE TABLE transfers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        photo_id INTEGER NOT NULL REFERENCES photos(id),
        started_at TEXT NOT NULL,
        completed_at TEXT,
        bytes_transferred INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'in_progress',
        error_message TEXT
    );
    CREATE INDEX idx_photos_device_status ON photos(device_id, status);
    CREATE INDEX idx_devices_token_hash ON devices(token_hash);
    """,
]


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        for target, script in enumerate(MIGRATIONS[version:], start=version + 1):
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {target}")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeviceStore:
    """Trusted-device persistence. Thread-safe (connection per call)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def upsert_device(
        self, device_id: str, name: str, platform: str, token_hash: str
    ) -> None:
        with _connect(self._db_path) as conn:
            conn.execute(
                """
                INSERT INTO devices (device_id, name, platform, token_hash, paired_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    name = excluded.name,
                    platform = excluded.platform,
                    token_hash = excluded.token_hash,
                    paired_at = excluded.paired_at,
                    is_trusted = 1
                """,
                (device_id, name, platform, token_hash, _utcnow()),
            )

    def trusted_devices(self) -> list[sqlite3.Row]:
        with _connect(self._db_path) as conn:
            return conn.execute(
                "SELECT * FROM devices WHERE is_trusted = 1 ORDER BY name"
            ).fetchall()

    def find_by_token_hash(self, token_hash: str) -> sqlite3.Row | None:
        with _connect(self._db_path) as conn:
            return conn.execute(
                "SELECT * FROM devices WHERE token_hash = ? AND is_trusted = 1",
                (token_hash,),
            ).fetchone()

    def touch_last_seen(self, device_id: str) -> None:
        with _connect(self._db_path) as conn:
            conn.execute(
                "UPDATE devices SET last_seen = ? WHERE device_id = ?",
                (_utcnow(), device_id),
            )
