"""Semantic version comparison (spec §23: 1.10.0 > 1.9.0)."""
from __future__ import annotations


def parse_version(text: str) -> tuple[int, ...]:
    """'1.10.0' -> (1, 10, 0). Non-numeric segments end the parse."""
    parts: list[int] = []
    for piece in text.strip().lstrip("v").split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts) if parts else (0,)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)
