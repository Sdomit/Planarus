"""Encryption for stored webhook signing secrets (P17.3).

Each webhook subscription's HMAC-SHA256 signing secret is a *recoverable*
credential — the server must hold the plaintext to sign every outgoing payload —
so it is encrypted at rest with Fernet (AES-128-CBC + HMAC), keyed by
``AGENTBOARD_WEBHOOK_ENC_KEY`` from the environment. That key is a forbidden path
the user configures; it is never logged, returned, or persisted anywhere but the
process env.

Webhooks are fully inert when the key is unset: ``is_enabled()`` is False, so the
delivery trigger short-circuits and the management routes 404 — no secret is ever
stored or reachable. ``cryptography`` is imported lazily (the optional [webhooks]
extra) so the default install doesn't need it.
"""
from __future__ import annotations

from app.core.config import settings


def is_enabled() -> bool:
    """True only when the webhook encryption key is configured — the master gate."""
    return bool(settings.webhook_enc_key)


def generate_key() -> str:
    """A fresh Fernet key (urlsafe base64) for the user to put in their .env."""
    from cryptography.fernet import Fernet  # lazy: only with the extra installed

    return Fernet.generate_key().decode()


def _fernet():
    from cryptography.fernet import Fernet  # lazy

    if not settings.webhook_enc_key:
        raise RuntimeError(
            "webhook secret encryption is not configured (set AGENTBOARD_WEBHOOK_ENC_KEY)"
        )
    return Fernet(settings.webhook_enc_key.encode())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
