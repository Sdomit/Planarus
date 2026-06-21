"""External API authentication + capability resolution (Phase 7C1).

Authenticates an incoming ``Authorization: Bearer agbk_<key_id>_<secret>`` against
an ``ApiClient`` row (Argon2id verify), resolves a Capability scoped to the
client's projects, and gates the request through the in-process rate limiter.

Security properties:
  * Malformed / unknown / disabled / revoked / expired keys all return the SAME
    generic 401, and every attempt performs exactly one Argon2 verification (a
    dummy verify for unknown/malformed key ids) so failure paths are not materially
    timing-distinguishable.
  * Scope (workspace + project ids + can_read/can_propose) comes from the credential
    row, never from the request.
  * Read routes require ``can_read``; proposal routes require ``can_propose``.
  * The limiter failing internally fails CLOSED (503).
  * Authorization headers, raw keys, verifiers, and secrets are never logged.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import NoReturn, Optional

from fastapi import Depends, Header, Request
from sqlmodel import Session, select

from app.api.external.problems import ExternalProblem
from app.core.rate_limit import limiter
from app.db.session import get_session
from app.mcp.capabilities import Capability, capability_from_api_client
from app.models.api_client import ApiClient
from app.services import api_credentials


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seconds_between(earlier_iso: str, later_iso: str) -> float:
    try:
        return (
            datetime.fromisoformat(later_iso) - datetime.fromisoformat(earlier_iso)
        ).total_seconds()
    except ValueError:
        return float("inf")  # unparseable → treat as long ago → allow update


def _project_ids(client: ApiClient) -> frozenset[str]:
    try:
        ids = json.loads(client.project_ids_json)
    except (json.JSONDecodeError, TypeError):
        return frozenset()
    return frozenset(p for p in ids if isinstance(p, str) and p)


def _ceil(seconds: float) -> int:
    return max(1, math.ceil(seconds))


def _limiter_call(fn, *args):
    """Call a limiter method; any internal failure fails CLOSED with 503."""
    try:
        return fn(*args)
    except Exception:  # noqa: BLE001 — limiter must never open the gate on error
        raise ExternalProblem(
            503,
            "limiter_unavailable",
            "Service Unavailable",
            "request throttling is temporarily unavailable",
        )


def _fail_auth() -> NoReturn:
    """Record a failed auth attempt and raise a generic 401 (or 429 if throttled)."""
    retry = _limiter_call(limiter.note_auth_failure)
    if retry is not None:
        raise ExternalProblem(
            429,
            "rate_limited",
            "Too Many Requests",
            "authentication attempts are temporarily throttled",
            retry_after=_ceil(retry),
        )
    raise ExternalProblem(401, "unauthorized", "Unauthorized", "invalid or missing API key")


def _touch_last_used(session: Session, client: ApiClient) -> None:
    """Update last_used_at opportunistically, at most once per minute per client."""
    now = _now_iso()
    if client.last_used_at is None or _seconds_between(client.last_used_at, now) >= 60:
        client.last_used_at = now
        session.add(client)
        session.commit()


def _authenticate(
    request: Request, session: Session, authorization: Optional[str]
) -> tuple[ApiClient, Capability]:
    parsed = api_credentials.parse_authorization(authorization)
    if parsed is None:
        api_credentials.dummy_verify()
        _fail_auth()
    key_id, secret = parsed

    client = session.exec(
        select(ApiClient).where(ApiClient.key_id == key_id)
    ).first()
    if client is None:
        api_credentials.dummy_verify()
        _fail_auth()

    if not api_credentials.verify_secret(client.secret_hash, secret):
        _fail_auth()

    # Same generic 401 for disabled / revoked / expired (a real verify already ran).
    if (
        not client.enabled
        or client.revoked_at is not None
        or _now_iso() >= client.expires_at
    ):
        _fail_auth()

    _touch_last_used(session, client)
    cap = capability_from_api_client(
        workspace_id=client.workspace_id,
        key_id=client.key_id,
        project_ids=_project_ids(client),
        label=client.label,
        can_read=client.can_read,
        can_propose=client.can_propose,
    )
    return client, cap


def _rate_and_concurrency(client: ApiClient, *, propose: bool):
    """Apply the per-key rate + concurrency gate. Yields nothing; releases on exit."""
    check = limiter.check_propose if propose else limiter.check_read
    label = "proposal" if propose else "read"
    retry = _limiter_call(check, client.key_id)
    if retry is not None:
        raise ExternalProblem(
            429,
            "rate_limited",
            "Too Many Requests",
            f"{label} rate limit exceeded",
            retry_after=_ceil(retry),
        )
    if not _limiter_call(limiter.acquire, client.key_id):
        raise ExternalProblem(
            429,
            "rate_limited",
            "Too Many Requests",
            "concurrent request limit exceeded",
            retry_after=1,
        )


def require_external_read(
    request: Request,
    session: Session = Depends(get_session),
    authorization: Optional[str] = Header(default=None),
):
    """Dependency for external read routes: auth + can_read + rate + concurrency."""
    client, cap = _authenticate(request, session, authorization)
    if not cap.can_read:
        raise ExternalProblem(
            403, "forbidden", "Forbidden", "this API key does not have read access"
        )
    _rate_and_concurrency(client, propose=False)
    try:
        yield cap
    finally:
        try:
            limiter.release(client.key_id)
        except Exception:  # noqa: BLE001 — release must never raise into the response
            pass


def require_external_propose(
    request: Request,
    session: Session = Depends(get_session),
    authorization: Optional[str] = Header(default=None),
):
    """Dependency for external proposal routes: auth + can_propose + rate + concurrency."""
    client, cap = _authenticate(request, session, authorization)
    if not cap.can_propose:
        raise ExternalProblem(
            403, "forbidden", "Forbidden", "this API key does not have propose access"
        )
    _rate_and_concurrency(client, propose=True)
    try:
        yield cap
    finally:
        try:
            limiter.release(client.key_id)
        except Exception:  # noqa: BLE001
            pass
