"""FastAPI auth dependencies (Phase 10.1, hosted mode).

These sit at the HTTP boundary and enforce *who may call what*. They are only
reached on the auth/members routes, which are mounted always but gated by
``require_auth_enabled`` — so when ``AGENTBOARD_AUTH_ENABLED`` is off the whole
surface returns 404 and the app behaves exactly as the local single-user tool.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from app.core import actor
from app.core.config import settings
from app.db.session import get_session
from app.models.user import User
from app.services import auth_service


def require_auth_enabled() -> None:
    """404 the whole auth surface unless hosted-mode auth is enabled."""
    if not settings.auth_enabled:
        raise HTTPException(status_code=404, detail="not found")


async def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """Resolve the caller from the session cookie; 401 if missing/invalid/expired.

    Async so the actor context is set in the event-loop task and reaches the
    audit writes of sync endpoints (P16.0, D32 — see app/core/actor.py).
    """
    raw_token = request.cookies.get(auth_service.SESSION_COOKIE)
    user = auth_service.resolve_user(session, raw_token)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    actor.set_current_actor_id(user.id)
    return user


def require_workspace_role(
    session: Session, workspace_id: str, user: User, *allowed_roles: str
) -> str:
    """Return the caller's role in the workspace, or 403 if it isn't allowed.

    A non-member is treated the same as a disallowed role (403), never revealing
    whether the workspace exists to an outsider beyond the caller's own view.
    """
    role = auth_service.role_in_workspace(session, workspace_id, user.id)
    if role is None or role not in allowed_roles:
        raise HTTPException(status_code=403, detail="insufficient workspace role")
    return role
