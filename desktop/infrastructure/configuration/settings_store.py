"""JSON-backed settings persistence with atomic writes.

Lives at %LOCALAPPDATA%\\PixSynq\\settings.json. Also owns the
installation ID (random UUID, generated once per installation — spec §5).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(self._data, dict):
                raise ValueError("settings root must be an object")
        except FileNotFoundError:
            self._data = {}
        except (ValueError, OSError) as exc:
            # Corrupt settings must not brick the app; keep the bad file
            # aside for diagnostics and start fresh.
            log.warning("Unreadable settings file (%s); starting fresh", exc)
            try:
                self._path.rename(self._path.with_suffix(".json.bad"))
            except OSError:
                pass
            self._data = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)
        self._save()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix="settings.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp_name, self._path)
        except OSError:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # -- Well-known settings -------------------------------------------

    @property
    def installation_id(self) -> str:
        existing = self.get("installation_id")
        if existing:
            return existing
        new_id = str(uuid.uuid4())
        self.set("installation_id", new_id)
        return new_id

    @property
    def setup_complete(self) -> bool:
        return bool(self.get("setup_complete", False))

    def mark_setup_complete(self) -> None:
        self.set("setup_complete", True)

    @property
    def destination_dir(self) -> Path | None:
        raw = self.get("destination_dir")
        return Path(raw) if raw else None

    def set_destination_dir(self, path: Path) -> None:
        self.set("destination_dir", str(path))
