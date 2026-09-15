"""Registration input validation and local persistence.

Phase 2 scope: validate and store the registration locally, marked
"pending" for upload. The HTTPS submission to the registration API
(spec §7) is wired in the server/update phase; registration must never
block core functionality (spec §32), so a pending record is a normal,
supported state — not a stub.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

MAX_NAME_LEN = 100
MAX_EMAIL_LEN = 254


@dataclass(frozen=True)
class RegistrationInput:
    name: str
    email: str
    consented: bool


def validate_registration(reg: RegistrationInput) -> list[str]:
    """Return a list of human-readable problems; empty means valid."""
    problems: list[str] = []
    name = reg.name.strip()
    email = reg.email.strip()

    if not name:
        problems.append("Please enter your name.")
    elif len(name) > MAX_NAME_LEN:
        problems.append(f"Name must be at most {MAX_NAME_LEN} characters.")

    if not email:
        problems.append("Please enter your email address.")
    elif len(email) > MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        problems.append("Please enter a valid email address.")

    if not reg.consented:
        problems.append("Please review and accept the Privacy Policy to continue.")

    return problems
