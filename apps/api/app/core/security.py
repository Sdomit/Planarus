"""Local control-plane protection for state-changing endpoints (Phase 7A).

Phase 7A is local-only and single-user, but approve/reject/apply/invalidate
change canonical state. We defend against *browser cross-site* requests to the
loopback API with two checks on every state-changing call:

  1. an in-memory, per-process control token (header ``X-Approvo-Local-Token``);
  2. an Origin allowlist (the packaged/local UI origins only).

This does NOT defend against a malicious *local process* — such a process can
already read the SQLite file directly; that is explicitly out of scope for the
local-first MVP. The token is generated once per process, kept in memory only,
and is never written to the DB, files, logs, AuditEvent payloads, error
responses, or prompts.
"""
from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, Request

from app.core.config import settings

# The only origins the local UI is served from in dev/desktop. Shared with the
# CORS middleware in app.main so the two never drift.
LOCAL_UI_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://localhost:3000",
)


def allowed_ui_origins() -> tuple[str, ...]:
    """Local dev origins plus any hosted web origins configured via
    ``AGENTBOARD_WEB_ORIGINS`` (P10.4). Empty config → just the local origins, so
    local behavior is unchanged.
    """
    extra = tuple(
        o.strip() for o in settings.web_origins.split(",") if o.strip()
    )
    return LOCAL_UI_ORIGINS + extra

# Generated once at import (process start); in-memory only. Never persisted.
_LOCAL_CONTROL_TOKEN: str = secrets.token_urlsafe(32)


def get_local_control_token() -> str:
    return _LOCAL_CONTROL_TOKEN


def origin_allowed(origin: str | None) -> bool:
    """A missing Origin (non-browser client) passes; a present one must match.

    Browsers always send Origin on cross-origin requests (the UI on :5173 calling
    the API on another port is cross-origin), so a forged/foreign Origin is
    rejected. Non-browser local callers (no Origin) are outside the browser
    threat model and are allowed.
    """
    return origin is None or origin in allowed_ui_origins()


def require_local_control(
    request: Request,
    x_approvo_local_token: str | None = Header(default=None),
) -> None:
    """FastAPI dependency guarding state-changing approval endpoints.

    Order matters: an unexpected Origin fails 403 regardless of the token;
    otherwise a missing/invalid token fails 401.
    """
    if not origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="origin not allowed")
    if not x_approvo_local_token or not secrets.compare_digest(
        x_approvo_local_token, _LOCAL_CONTROL_TOKEN
    ):
        raise HTTPException(
            status_code=401, detail="invalid or missing local control token"
        )
