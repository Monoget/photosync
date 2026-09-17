"""Photo destination folder selection helpers and validation."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FolderCheck:
    ok: bool
    reason: str = ""


def default_destination() -> Path:
    """Suggest <user Pictures>\\PixSynq (never inside the install dir)."""
    home = Path.home()
    pictures = home / "Pictures"
    base = pictures if pictures.is_dir() else home
    return base / "PixSynq"


def validate_destination(path: Path) -> FolderCheck:
    """The folder must exist or be creatable, and be writable."""
    if str(path).strip() in ("", "."):  # Path("") stringifies to "."
        return FolderCheck(False, "No folder selected.")

    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FolderCheck(False, f"Folder cannot be created: {exc.strerror or exc}")

    probe = path / f".pixsynq-write-test-{uuid.uuid4().hex[:8]}"
    try:
        probe.write_bytes(b"")
    except OSError:
        return FolderCheck(False, "PixSynq does not have permission to write here.")
    finally:
        try:
            os.unlink(probe)
        except OSError:
            pass

    return FolderCheck(True)
