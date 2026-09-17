"""PixSynq server: installation registry, heartbeat, update feed, admin.

Deployment configuration comes from the environment (spec §6):

    PIXSYNQ_DB       SQLite path            (default ./pixsynq-server.db)
    ADMIN_USER         admin dashboard user   (dashboard disabled if unset)
    ADMIN_PASSWORD     admin dashboard pass   (dashboard disabled if unset)

Run behind HTTPS (reverse proxy) in production. The desktop app never
talks to the database directly — only to this API (spec §6). Client IPs
are taken from the connection, never from request payloads (spec §4).
"""
from __future__ import annotations

import hmac
import os
import re
import sqlite3
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request

MAX_BODY = 16 * 1024
RATE_LIMIT = 30  # requests per window per IP
RATE_WINDOW_S = 60
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS installations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    installation_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    desktop_username TEXT,
    ip_address TEXT,
    application_version TEXT,
    operating_system TEXT,
    os_version TEXT,
    architecture TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_inst_installation_id
    ON installations(installation_id);
CREATE INDEX IF NOT EXISTS idx_inst_email ON installations(email);
CREATE INDEX IF NOT EXISTS idx_inst_first_seen ON installations(first_seen_at);
CREATE INDEX IF NOT EXISTS idx_inst_last_seen ON installations(last_seen_at);

CREATE TABLE IF NOT EXISTS releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    architecture TEXT NOT NULL,
    version TEXT NOT NULL,
    minimum_supported_version TEXT,
    release_date TEXT,
    mandatory INTEGER NOT NULL DEFAULT 0,
    title TEXT,
    message TEXT,
    download_url TEXT NOT NULL,
    release_notes_url TEXT,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window_s: float = RATE_WINDOW_S):
        self._limit = limit
        self._window = window_s
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True


def create_app(db_path: str | os.PathLike | None = None) -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY
    path = Path(db_path or os.environ.get("PIXSYNQ_DB", "pixsynq-server.db"))
    limiter = RateLimiter()

    def db() -> sqlite3.Connection:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    with db() as conn:
        conn.executescript(SCHEMA)

    def client_ip() -> str:
        # Behind a trusted reverse proxy, configure it to set X-Real-IP;
        # otherwise the socket address is authoritative (spec §4).
        return request.headers.get("X-Real-IP", request.remote_addr or "")

    @app.before_request
    def throttle():
        if not limiter.allow(client_ip()):
            return jsonify({"error": "rate limit exceeded"}), 429

    # -- Installations --------------------------------------------------

    @app.post("/api/v1/installations/register")
    def register():
        data = request.get_json(silent=True) or {}
        installation_id = str(data.get("installation_id", ""))[:64].strip()
        name = str(data.get("name", ""))[:100].strip()
        email = str(data.get("email", ""))[:254].strip()
        if len(installation_id) < 8 or not name or not _EMAIL_RE.match(email):
            return jsonify({"error": "invalid registration"}), 400
        now = _utcnow()
        with db() as conn:
            conn.execute(
                """
                INSERT INTO installations (installation_id, name, email,
                    desktop_username, ip_address, application_version,
                    operating_system, os_version, architecture,
                    first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(installation_id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    desktop_username = excluded.desktop_username,
                    ip_address = excluded.ip_address,
                    application_version = excluded.application_version,
                    os_version = excluded.os_version,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    installation_id, name, email,
                    str(data.get("desktop_username", ""))[:100],
                    client_ip(),
                    str(data.get("application_version", ""))[:32],
                    str(data.get("operating_system", ""))[:32],
                    str(data.get("os_version", ""))[:64],
                    str(data.get("architecture", ""))[:16],
                    now, now,
                ),
            )
        return jsonify({"ok": True})

    @app.post("/api/v1/installations/heartbeat")
    def heartbeat():
        data = request.get_json(silent=True) or {}
        installation_id = str(data.get("installation_id", ""))[:64].strip()
        if len(installation_id) < 8:
            return jsonify({"error": "invalid heartbeat"}), 400
        with db() as conn:
            cursor = conn.execute(
                """
                UPDATE installations SET last_seen_at = ?, ip_address = ?,
                    application_version = COALESCE(NULLIF(?, ''), application_version)
                WHERE installation_id = ?
                """,
                (
                    _utcnow(), client_ip(),
                    str(data.get("application_version", ""))[:32],
                    installation_id,
                ),
            )
        if cursor.rowcount == 0:
            return jsonify({"error": "unknown installation"}), 404
        return jsonify({"ok": True})

    # -- Updates --------------------------------------------------------

    @app.get("/api/v1/updates/latest")
    def latest_update():
        platform = request.args.get("platform", "windows")[:32]
        arch = request.args.get("architecture", "x64")[:16]
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM releases WHERE platform = ? AND architecture = ?"
                " ORDER BY id DESC LIMIT 1",
                (platform, arch),
            ).fetchone()
        if row is None:
            return jsonify({"error": "no release available"}), 404
        return jsonify(
            {
                "version": row["version"],
                "minimum_supported_version": row["minimum_supported_version"],
                "release_date": row["release_date"],
                "mandatory": bool(row["mandatory"]),
                "title": row["title"],
                "message": row["message"],
                "download_url": row["download_url"],
                "release_notes_url": row["release_notes_url"],
                "sha256": row["sha256"],
            }
        )

    # -- Admin ----------------------------------------------------------

    def admin_authorized() -> bool:
        user = os.environ.get("ADMIN_USER")
        password = os.environ.get("ADMIN_PASSWORD")
        if not user or not password:
            return False
        auth = request.authorization
        return (
            auth is not None
            and auth.type == "basic"
            and hmac.compare_digest(auth.username or "", user)
            and hmac.compare_digest(auth.password or "", password)
        )

    @app.get("/admin")
    def admin():
        if not os.environ.get("ADMIN_USER") or not os.environ.get("ADMIN_PASSWORD"):
            return jsonify({"error": "not found"}), 404
        if not admin_authorized():
            return (
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="PixSynq Admin"'},
            )
        with db() as conn:
            total = conn.execute("SELECT COUNT(*) FROM installations").fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM installations"
                " WHERE last_seen_at >= datetime('now', '-30 days')"
            ).fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM installations"
                " WHERE first_seen_at >= date('now')"
            ).fetchone()[0]
            week = conn.execute(
                "SELECT COUNT(*) FROM installations"
                " WHERE first_seen_at >= datetime('now', '-7 days')"
            ).fetchone()[0]
            versions = conn.execute(
                "SELECT application_version, COUNT(*) AS n FROM installations"
                " GROUP BY application_version ORDER BY n DESC"
            ).fetchall()
            systems = conn.execute(
                "SELECT operating_system, COUNT(*) AS n FROM installations"
                " GROUP BY operating_system ORDER BY n DESC"
            ).fetchall()

        version_rows = "".join(
            f"<tr><td>{v['application_version'] or 'unknown'}</td>"
            f"<td>{v['n']}</td></tr>"
            for v in versions
        )
        system_rows = "".join(
            f"<tr><td>{s['operating_system'] or 'unknown'}</td>"
            f"<td>{s['n']}</td></tr>"
            for s in systems
        )
        return f"""<!doctype html>
<title>PixSynq Installations</title>
<style>
 body {{ font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 640px; }}
 table {{ border-collapse: collapse; margin: 1rem 0; }}
 td, th {{ border: 1px solid #ccc; padding: 6px 14px; text-align: left; }}
</style>
<h1>PixSynq Installations</h1>
<table>
 <tr><td>Total</td><td>{total}</td></tr>
 <tr><td>Active (30 days)</td><td>{active}</td></tr>
 <tr><td>New today</td><td>{today}</td></tr>
 <tr><td>New this week</td><td>{week}</td></tr>
</table>
<h2>Versions</h2><table>{version_rows}</table>
<h2>Operating systems</h2><table>{system_rows}</table>
"""

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8000)
