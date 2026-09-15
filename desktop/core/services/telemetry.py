"""Registration upload and heartbeat (spec §4, §9).

Everything here is best-effort: PhotoSync works fully without the
server (spec §32), and nothing runs unless the user completed the
consent flow and an API base URL is configured via deployment
configuration (API_BASE_URL env var or the "api_base_url" setting).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from infrastructure.configuration.settings_store import SettingsStore

log = logging.getLogger(__name__)

HEARTBEAT_INTERVAL = timedelta(hours=24)


def api_base(settings: SettingsStore) -> str | None:
    return os.environ.get("API_BASE_URL") or settings.get("api_base_url")


def _post(url: str, payload: dict) -> bool:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "PhotoSync"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def sync_registration(settings: SettingsStore, app_version: str) -> None:
    """Upload a pending registration; send a daily heartbeat otherwise."""
    base = api_base(settings)
    if base is None:
        return
    base = base.rstrip("/")

    registration = settings.get("registration")
    if registration and registration.get("upload_status") == "pending":
        ok = _post(
            f"{base}/api/v1/installations/register",
            {
                "installation_id": settings.installation_id,
                "name": registration.get("name", ""),
                "email": registration.get("email", ""),
                "desktop_username": registration.get("desktop_username", ""),
                "application_version": app_version,
                "operating_system": "Windows",
                "os_version": platform.version(),
                "architecture": platform.machine(),
            },
        )
        if ok:
            registration = dict(registration, upload_status="uploaded")
            settings.set("registration", registration)
            settings.set("last_heartbeat", datetime.now(timezone.utc).isoformat())
            log.info("Registration uploaded")
        else:
            log.info("Registration upload failed; will retry next start")
        return

    last = settings.get("last_heartbeat")
    if last:
        try:
            if datetime.now(timezone.utc) - datetime.fromisoformat(last) \
                    < HEARTBEAT_INTERVAL:
                return
        except ValueError:
            pass
    # Heartbeats carry no name/email (spec §9)
    if _post(
        f"{base}/api/v1/installations/heartbeat",
        {
            "installation_id": settings.installation_id,
            "application_version": app_version,
        },
    ):
        settings.set("last_heartbeat", datetime.now(timezone.utc).isoformat())


def sync_registration_async(settings: SettingsStore, app_version: str) -> None:
    threading.Thread(
        target=sync_registration,
        args=(settings, app_version),
        daemon=True,
        name="telemetry",
    ).start()
