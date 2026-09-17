"""Per-user application data locations.

User data lives under %LOCALAPPDATA%\\PixSynq (never in the install
directory, never alongside the photos themselves).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path

    @classmethod
    def default(cls) -> "AppPaths":
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            base = Path(local_appdata)
        else:  # non-Windows dev environment fallback
            base = Path.home() / ".local" / "share"
        return cls(data_dir=base / "PixSynq")

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "pixsynq.db"

    @property
    def settings_path(self) -> Path:
        return self.data_dir / "settings.json"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
