"""Destination file naming: sanitization and year/month organization."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MAX_NAME_LEN = 120


def sanitize_filename(name: str) -> str:
    """Reduce an untrusted filename to a safe basename."""
    # Take the basename across both separator conventions.
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _FORBIDDEN.sub("_", name).strip(" .")
    if not name or set(name) <= {"_", "."}:
        return "photo.jpg"
    if len(name) > MAX_NAME_LEN:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: MAX_NAME_LEN - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_NAME_LEN]
    return name


def dest_path_for(root: Path, filename: str, taken_at: datetime | None) -> Path:
    """<root>/YYYY/MM/<name>, uniquified if a different file already sits there."""
    taken = taken_at or datetime.now(timezone.utc)
    folder = root / f"{taken.year:04d}" / f"{taken.month:02d}"
    safe = sanitize_filename(filename)
    candidate = folder / safe
    if not candidate.exists():
        return candidate
    stem, dot, ext = safe.rpartition(".")
    if not dot:
        stem, ext = safe, ""
    for n in range(1, 10_000):
        candidate = folder / (f"{stem} ({n}).{ext}" if ext else f"{stem} ({n})")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"Cannot find a free name for {safe} in {folder}")
