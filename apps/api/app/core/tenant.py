"""Request-scoped tenant enforcement (Phase 10.2, hosted mode).

The workspace is the tenant boundary (D19). These helpers gate access to
workspaces, projects, and the approve/apply path by the caller's membership role.

**All enforcement is a no-op when `AGENTBOARD_AUTH_ENABLED` is off** — the local
single-user tool is unchanged. When auth is on, `tenant_user` requires a valid
session on the domain routes and the `require_*` helpers 403 a caller whose
workspace role isn't allowed.

Coverage note (honest scope): this slice enforces the crown-jewel boundaries —
workspace/project access + the D22 approver gate on approve/apply. Exhaustive
per-child-route guards (individual task/phase/etc. endpoints) are the mechanical
follow-on **P10.2b**; until then, with auth enabled, treat multi-tenant isolation
as incomplete (there is no hosted deployment yet — auth is off by default).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlmodel import Session, select

from app.core.config import settings
from app.db.session import get_session
from app.models.project import Project
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.services import auth_service

# Role sets by capability (owner ⊃ editor ⊃ viewer).
READ_ROLES = ("owner", "editor", "viewer")
WRITE_ROLES = ("owner", "editor")
APPROVER_ROLES = ("owner",)


def tenant_user(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    """Resolve the caller on a domain route.

    Auth disabled → ``None`` (local mode, no enforcement). Auth enabled → the
    authenticated user, or 401 if the session cookie is missing/invalid. Unlike
    ``auth_deps.require_auth_enabled`` this never 404s: domain routes must keep
    working in local mode.
    """
    if not settings.auth_enabled:
        return None
    raw_token = request.cookies.get(auth_service.SESSION_COOKIE)
    user = auth_service.resolve_user(session, raw_token)
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return user


def user_workspace_ids(session: Session, user: User) -> set[str]:
    rows = session.exec(
        select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user.id
        )
    ).all()
    return set(rows)


def require_workspace_access(
    session: Session,
    workspace_id: str,
    user: Optional[User],
    *allowed_roles: str,
) -> Optional[str]:
    """403 unless the caller holds an allowed role in the workspace.

    No-op (returns None) when auth is disabled. A non-member is treated exactly
    like a disallowed role — 403, not 404 — so workspace existence isn't leaked.
    """
    if not settings.auth_enabled:
        return None
    role = auth_service.role_in_workspace(session, workspace_id, user.id)  # type: ignore[union-attr]
    if role is None or role not in allowed_roles:
        raise HTTPException(status_code=403, detail="insufficient workspace role")
    return role


def require_project_access(
    session: Session,
    project: Project,
    user: Optional[User],
    *allowed_roles: str,
) -> Optional[str]:
    """403 unless the caller holds an allowed role in the project's workspace.

    Everything under a project (phases, tasks, …) scopes through this one check,
    so guarding project access guards the subtree. No-op when auth is disabled.
    """
    return require_workspace_access(
        session, project.workspace_id, user, *allowed_roles
    )
