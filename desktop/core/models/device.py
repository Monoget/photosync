"""Device models."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiscoveredDevice:
    """A PixSynq peer seen on the local network (not necessarily paired)."""

    service_name: str
    display_name: str
    address: str
    port: int
    platform: str = "unknown"
    protocol_version: int | None = None
