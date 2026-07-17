"""Encryption for stored OAuth tokens (Phase 15.12b).

Calendar-sync refresh/access tokens are long-lived credentials to the user's
external calendar, so they are encrypted at rest with Fernet (AES-128-CBC +
HMAC). The key comes from `AGENTBOARD_CALENDAR_ENC_KEY` in the environment — a
forbidden path the user configures; it is never logged, returned, or persisted
anywhere but the process env.

Sync is fully inert when the key is unset: `is_enabled()` is False and the sync
routes 404, so tokens are never even reachable. `cryptography` is imported lazily
(the optional `[calendar-sync]` extra) so the default install doesn't need it.
"""
from __future__ import annotations

from app.core.config import settings


def is_enabled() -> bool:
    """True only when an encryption key is configured — the master gate for sync."""
    return bool(settings.calendar_enc_key)


def generate_key() -> str:
    """A fresh Fernet key (urlsafe base64) for the user to put in their .env."""
    from cryptography.fernet import Fernet  # lazy: only with the extra installed

    return Fernet.generate_key().decode()


def _fernet():
    from cryptography.fernet import Fernet  # lazy

    if not settings.calendar_enc_key:
        raise RuntimeError(
            "calendar token encryption is not configured "
            "(set AGENTBOARD_CALENDAR_ENC_KEY)"
        )
    return Fernet(settings.calendar_enc_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
