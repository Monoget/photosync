"""Admin CLI: publish a release row for the update feed.

Usage:
    python add_release.py --version 1.1.0 --url https://.../PixSynq-1.1.0.exe \
        --sha256 <hex> [--title ...] [--message ...] [--mandatory]
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True, dest="download_url")
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--platform", default="windows")
    parser.add_argument("--architecture", default="x64")
    parser.add_argument("--minimum", default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--message", default=None)
    parser.add_argument("--notes-url", default=None)
    parser.add_argument("--mandatory", action="store_true")
    args = parser.parse_args()

    db = Path(os.environ.get("PIXSYNQ_DB", "pixsynq-server.db"))
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO releases (platform, architecture, version,
                minimum_supported_version, release_date, mandatory, title,
                message, download_url, release_notes_url, sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                args.platform, args.architecture, args.version, args.minimum,
                datetime.now(timezone.utc).date().isoformat(),
                int(args.mandatory),
                args.title or f"PixSynq {args.version}",
                args.message or "", args.download_url, args.notes_url,
                args.sha256.lower(), datetime.now(timezone.utc).isoformat(),
            ),
        )
    print(f"Published {args.version} for {args.platform}/{args.architecture}")


if __name__ == "__main__":
    main()
