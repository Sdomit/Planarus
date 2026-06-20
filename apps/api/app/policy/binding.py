"""Canonical serialization + checksums that bind a proposal to its target state.

These make a proposal *immutable and stale-detectable*: the patch checksum pins
exactly what will be applied, and the target fingerprint pins the relevant
current state of the target so any later human edit is detected at apply time.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from app.core.utils import sha256_hex


def canonical_json(obj: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators, UTF-8 friendly."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def patch_checksum(normalized_patch: dict) -> str:
    return sha256_hex(canonical_json(normalized_patch))


def target_fingerprint(allowed_fields: Iterable[str], target: Any) -> str:
    """Fingerprint of the target's mutable surface plus its ``updated_at``.

    Any human edit to a relevant field — or any save that bumps ``updated_at`` —
    changes the fingerprint, so a stale proposal fails the compare-and-swap check
    at apply time.
    """
    snapshot = {field: getattr(target, field, None) for field in sorted(allowed_fields)}
    snapshot["__updated_at__"] = getattr(target, "updated_at", None)
    return sha256_hex(canonical_json(snapshot))
