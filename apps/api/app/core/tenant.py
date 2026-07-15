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


# --- P10.2b: one registry-driven guard for every project-scoped domain route ---
# Maps a route path/query parameter to a resolver returning the owning
# ``project_id`` (or None if the entity doesn't exist). Applied uniformly via
# ``include_router(..., dependencies=[Depends(tenant_guard)])`` in the v1 router,
# so each domain route is guarded without a per-route edit. A route that carries
# none of these identifiers (a global/static route) is left untouched.
def _project_id_via(session: Session, model, entity_id: str, attr: str = "project_id"):
    from typing import Any

    obj: Any = session.get(model, entity_id)
    return getattr(obj, attr) if obj is not None else None


def _checklist_project_id(session: Session, item_id: str):
    from app.models.checklist_item import ChecklistItem
    from app.models.task import Task

    item = session.get(ChecklistItem, item_id)
    if item is None:
        return None
    task = session.get(Task, item.task_id)
    return task.project_id if task is not None else None


def _build_resolvers() -> dict:
    from app.models.agent_run import AgentRun
    from app.models.blocker import Blocker
    from app.models.context_file import ContextFile
    from app.models.decision import Decision
    from app.models.doc import Doc
    from app.models.milestone import Milestone
    from app.models.notification_rule import NotificationRule
    from app.models.phase import Phase
    from app.models.risk import Risk
    from app.models.stage import Stage
    from app.models.task import Task

    return {
        "project_id": lambda s, v: v if s.get(Project, v) is not None else None,
        "phase_id": lambda s, v: _project_id_via(s, Phase, v),
        "stage_id": lambda s, v: _project_id_via(s, Stage, v),
        "task_id": lambda s, v: _project_id_via(s, Task, v),
        "decision_id": lambda s, v: _project_id_via(s, Decision, v),
        "risk_id": lambda s, v: _project_id_via(s, Risk, v),
        "blocker_id": lambda s, v: _project_id_via(s, Blocker, v),
        "milestone_id": lambda s, v: _project_id_via(s, Milestone, v),
        "doc_id": lambda s, v: _project_id_via(s, Doc, v),
        "run_id": lambda s, v: _project_id_via(s, AgentRun, v),
        "rule_id": lambda s, v: _project_id_via(s, NotificationRule, v),
        "context_file_id": lambda s, v: _project_id_via(s, ContextFile, v),
        "item_id": _checklist_project_id,
    }


_RESOLVERS: Optional[dict] = None


def tenant_guard(
    request: Request,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> None:
    """Guard a project-scoped domain route by the caller's workspace role.

    Resolves the owning project from whichever identifier the route carries (a
    path param, or a ``project_id`` query param), then enforces READ roles for
    GET/HEAD and WRITE roles for mutations. No-op when auth is disabled; 404 if the
    referenced entity doesn't exist; leaves genuinely global routes (no tenant
    identifier) untouched.
    """
    if not settings.auth_enabled:
        return
    global _RESOLVERS
    if _RESOLVERS is None:
        _RESOLVERS = _build_resolvers()

    project_id = None
    matched = False
    for name, resolve in _RESOLVERS.items():
        if name in request.path_params:
            matched = True
            project_id = resolve(session, request.path_params[name])
            break
    if not matched:
        qp = request.query_params.get("project_id")
        if qp is not None:
            matched = True
            project_id = _RESOLVERS["project_id"](session, qp)
    if not matched:
        return  # no tenant-scoped identifier on this route

    if project_id is None:
        raise HTTPException(status_code=404, detail="not found")
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="not found")
    roles = READ_ROLES if request.method in ("GET", "HEAD") else WRITE_ROLES
    require_project_access(session, project, user, *roles)
