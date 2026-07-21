"""FastAPI auth dependencies (Phase 10.1, hosted mode).

These sit at the HTTP boundary and enforce *who may call what*. They are only
reached on the auth/members routes, which are mounted always but gated by
``require_auth_enabled`` — so when ``PLANARUS_AUTH_ENABLED`` is off the whole
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

    P16.1 (D29): a session running on an admin-issued temp password may only
    use the auth surface (login/me/change/logout) until the password is
    rotated; every other route answers 403.
    """
    raw_token = request.cookies.get(auth_service.SESSION_COOKIE)
    user = auth_service.resolve_user(session, raw_token)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    if not request.url.path.startswith("/api/v1/auth/"):
        reject_password_must_change(session, user)
    actor.set_current_actor_id(user.id)
    return user


def reject_password_must_change(session: Session, user: User) -> None:
    """403 while the account still runs on an admin-issued temp password."""
    if auth_service.password_must_change(session, user.id):
        raise HTTPException(status_code=403, detail="password change required")


async def require_server_admin(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """The admin-plane gate (P16.1, D29/D31): a signed-in, active server admin.

    403 for a valid non-admin session. Only ever mounted behind
    ``require_auth_enabled``, so in local mode the surface 404s before this
    runs — admin authority governs accounts, never project data.
    """
    user = await get_current_user(request, session)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="server admin required")
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
