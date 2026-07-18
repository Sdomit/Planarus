"""External API-key credential service (Phase 7C1).

Issues and verifies external API keys with the format

    agbk_<public_key_id>_<secret>

* ``public_key_id`` is a non-secret, indexed, log-safe lookup handle.
* ``secret`` is 32 bytes of CSPRNG entropy, URL-safe encoded.

Only an **Argon2id** encoded verifier of the secret is persisted (column
``ApiClient.secret_hash``). The raw key is returned exactly once at creation and
is never stored, logged, echoed, or placed in audit records.

The generic helpers here (``hash_secret`` / ``verify_secret`` / ``dummy_verify``)
are also reused by the P11.1 local email+password provider (``auth_service``) so
the whole app has exactly one locked Argon2id profile.

Honest scope note: like the Phase 7A local control token, this is a credential
guard for the local-first surface — it is not a substitute for a network firewall
or transport security. The external API is loopback-bound and disabled by default.
"""
from __future__ import annotations

import secrets
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from argon2.low_level import Type

# Key wire format.
KEY_PREFIX = "agbk"
_KEY_ID_BYTES = 16  # 32 hex chars — non-secret, indexed, safe to log
_SECRET_BYTES = 32  # secret entropy (locked)

# Explicit Argon2id parameters (NEVER the package defaults). Profile is locked by
# the Phase 7C1 spec; do not weaken it if hashing is slow — stop and report.
ARGON2_TIME_COST = 2
ARGON2_MEMORY_COST = 19456  # KiB (~19 MiB)
ARGON2_PARALLELISM = 1
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16

_hasher = PasswordHasher(
    time_cost=ARGON2_TIME_COST,
    memory_cost=ARGON2_MEMORY_COST,
    parallelism=ARGON2_PARALLELISM,
    hash_len=ARGON2_HASH_LEN,
    salt_len=ARGON2_SALT_LEN,
    type=Type.ID,
)

# A real Argon2id hash of a throwaway secret, computed once. Verifying any wrong
# secret against it costs the same as a real verify, so an unknown/malformed key
# id is not materially distinguishable from a known-but-wrong-secret one by timing.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(_SECRET_BYTES))


def generate_key() -> tuple[str, str, str]:
    """Return ``(key_id, secret, full_key)``.

    ``full_key`` = ``agbk_<key_id>_<secret>`` is shown to the user exactly once.
    """
    key_id = secrets.token_hex(_KEY_ID_BYTES)  # hex → never contains '_'
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    return key_id, secret, f"{KEY_PREFIX}_{key_id}_{secret}"


def hash_secret(secret: str) -> str:
    """Return the Argon2id encoded verifier for ``secret`` (salt managed internally)."""
    return _hasher.hash(secret)


def parse_authorization(header: Optional[str]) -> Optional[tuple[str, str]]:
    """Strictly parse one ``Bearer agbk_<key_id>_<secret>`` credential.

    Returns ``(key_id, secret)`` or ``None`` for anything malformed. Never logs.
    The secret may itself contain ``_``/``-`` (URL-safe alphabet), so the token is
    split on the first two underscores only; ``key_id`` is hex and underscore-free.
    """
    if not header or not isinstance(header, str):
        return None
    parts = header.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        return None
    segments = parts[1].split("_", 2)
    if len(segments) != 3:
        return None
    prefix, key_id, secret = segments
    if prefix != KEY_PREFIX or not key_id or not secret:
        return None
    return key_id, secret


def verify_secret(secret_hash: str, secret: str) -> bool:
    """Verify ``secret`` against a stored Argon2id verifier. Never raises/leaks."""
    try:
        return _hasher.verify(secret_hash, secret)
    except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
        return False
    except Exception:  # noqa: BLE001 — defensive: any verify error is an auth failure
        return False


def dummy_verify() -> None:
    """Timing-equalizing Argon2 verify for unknown/malformed key ids.

    Always performs one Argon2id verification (which fails) so the auth-failure
    path for an unknown key id costs roughly the same as for a real key id.
    """
    try:
        _hasher.verify(_DUMMY_HASH, "invalid")
    except Exception:  # noqa: BLE001 — expected mismatch; swallow
        pass
