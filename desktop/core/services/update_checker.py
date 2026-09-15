"""Periodic update check against the official update API (spec §23-24).

The API location comes from deployment configuration, never source code:
the UPDATE_BASE_URL (or API_BASE_URL) environment variable, or the
"update_base_url" setting. With none configured the checker is disabled.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from typing import Callable

from PySide6.QtCore import QObject, Signal

from core.services.version import is_newer
from infrastructure.configuration.settings_store import SettingsStore

log = logging.getLogger(__name__)


def default_fetch(url: str) -> dict | None:
    request = urllib.request.Request(url, headers={"User-Agent": "PhotoSync"})
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            data = json.loads(resp.read())
            return data if isinstance(data, dict) else None
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError, OSError):
        log.info("Update check failed (server unreachable)")
        return None


class UpdateChecker(QObject):
    update_available = Signal(dict)

    def __init__(
        self,
        settings: SettingsStore,
        app_version: str,
        fetch: Callable[[str], dict | None] = default_fetch,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._app_version = app_version
        self._fetch = fetch

    @property
    def base_url(self) -> str | None:
        return (
            os.environ.get("UPDATE_BASE_URL")
            or os.environ.get("API_BASE_URL")
            or self._settings.get("update_base_url")
        )

    @property
    def enabled(self) -> bool:
        return (
            self.base_url is not None
            and bool(self._settings.get("update_check_auto", True))
        )

    def check_async(self) -> None:
        if not self.enabled:
            return
        threading.Thread(target=self.check, daemon=True, name="update-check").start()

    def check(self) -> dict | None:
        """Fetch the latest release; emit update_available when relevant."""
        base = self.base_url
        if base is None:
            return None
        info = self._fetch(
            f"{base.rstrip('/')}/api/v1/updates/latest?platform=windows&architecture=x64"
        )
        if not info or not isinstance(info.get("version"), str):
            return None
        version = info["version"]
        if not is_newer(version, self._app_version):
            return None
        # Do not nag about a version the user already dismissed (spec §24) —
        # unless the release is mandatory.
        skipped = self._settings.get("update_skipped_version")
        if skipped == version and not info.get("mandatory"):
            return None
        if self._settings.get("update_notify", True):
            self.update_available.emit(info)
        return info

    def skip_version(self, version: str) -> None:
        self._settings.set("update_skipped_version", version)
