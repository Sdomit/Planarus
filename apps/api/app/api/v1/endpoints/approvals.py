"""Local human approval API (Phase 7A).

Read endpoints (list/detail/audit) are local-read-only. State-changing endpoints
(approve/reject/apply/invalidate) require the in-memory local control token AND an
allowed Origin via ``require_local_control``. There is deliberately NO
proposal-creation endpoint in Phase 7A — proposals are created only through the
``approval_service`` internal seam.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlmodel import Session

from app.core import tenant
from app.core.config import settings
from app.core.security import (
    get_local_control_token,
    origin_allowed,
    require_local_control,
)
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.project import Project
from app.models.user import User
from app.schemas.approval import (
    ApprovalAuditEntry,
    ApprovalDetail,
    ApprovalSummary,
    LocalSessionResponse,
    RejectRequest,
)
from app.services import approval_service, audit_service, entity_registry

router = APIRouter()


# #103: nothing prunes ApprovalRequest, so this list grows without bound. The cap
# is deliberately generous — the queue UI splits one response into "pending" and
# "history" client-side, so a small default would silently empty the history view.
# Callers page with offset and read X-Total-Count / X-Has-More.
MAX_APPROVAL_ROWS = 200


def _summarize(session: Session, rows) -> list[ApprovalSummary]:
    """Coerce ApprovalRequest rows to summaries with decided_by resolved to a
    display name (P16.0, D32) and the target resolved to its title (#96).

    The legacy literal "local" simply misses the decided_by lookup and the display
    stays None. Both lookups are batched across the page — one query per entity
    type present — so a 200-row queue does not fan out into 200 selects."""
    items = [ApprovalSummary.model_validate(r) for r in rows]
    names = audit_service.display_names(session, (s.decided_by for s in items))

    wanted: dict[str, set[str]] = {}
    for s in items:
        if s.target_entity_type and s.target_entity_id:
            wanted.setdefault(s.target_entity_type, set()).add(s.target_entity_id)
    titles = entity_registry.titles_for(session, wanted)

    for s in items:
        s.decided_by_display = names.get(s.decided_by) if s.decided_by else None
        if s.target_entity_type and s.target_entity_id:
            s.target_title = titles.get((s.target_entity_type, s.target_entity_id))
    return items


def _decider(user: Optional[User]) -> str:
    """decided_by value for a human decision: the real user id in team/hosted
    mode, the historical literal "local" in local single-user mode."""
    return user.id if user is not None else "local"


def _require_approver(
    session: Session, approval_id: str, user: Optional[User]
) -> None:
    """D22: in hosted mode, approve/apply/reject/invalidate need an owner
    (approver) role in the approval's workspace — on top of the local control
    token. No-op when auth is disabled. Preserves the 7C1 invariant: this only
    gates the human apply path; external clients still never reach it.
    """
    if not tenant.settings.auth_enabled:
        return
    ar = approval_service.get_approval(session, approval_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="approval not found")
    tenant.require_workspace_access(
        session, ar.workspace_id, user, *tenant.APPROVER_ROLES
    )


@router.get("/local-session", response_model=LocalSessionResponse)
def local_session(request: Request) -> LocalSessionResponse:
    """Hand the per-process local control token to the local UI.

    A present-but-foreign Origin is rejected; the global CORS policy additionally
    prevents a browser from reading this response cross-site.
    """
    if not origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="origin not allowed")
    return LocalSessionResponse(token=get_local_control_token())


def _require_approval_read(session: Session, approval_id: str, user: Optional[User]):
    """Fetch an approval and require read access to its workspace (no-op when auth
    off). Returns the approval; raises 404 if missing."""
    ar = approval_service.get_approval(session, approval_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="approval not found")
    tenant.require_workspace_access(session, ar.workspace_id, user, *tenant.READ_ROLES)
    return ar


@router.get("/approvals", response_model=list[ApprovalSummary])
def list_approvals(
    response: Response,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(default=MAX_APPROVAL_ROWS, ge=1, le=MAX_APPROVAL_ROWS),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[ApprovalSummary]:
    # Hosted mode scopes the queue to one project the caller can read (a
    # workspace-wide or global queue would leak tenants).
    if settings.auth_enabled:
        if project_id is None:
            raise HTTPException(status_code=400, detail="project_id is required")
        project = session.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        tenant.require_project_access(session, project, user, *tenant.READ_ROLES)
    rows = approval_service.list_approvals(
        session, project_id=project_id, status=status, limit=limit, offset=offset
    )
    # The response body is a bare list (changing its shape would break every
    # existing client), so the paging facts ride in headers. Without these a cap
    # is a silent truncation — the caller cannot tell a complete page from a
    # clipped one.
    total = approval_service.count_approvals(
        session, project_id=project_id, status=status
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Has-More"] = "true" if offset + len(rows) < total else "false"
    return _summarize(session, rows)


@router.get("/approvals/{approval_id}", response_model=ApprovalDetail)
def get_approval(
    approval_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ApprovalDetail:
    ar = _require_approval_read(session, approval_id, user)
    diff = approval_service.build_diff(session, ar)
    is_expired, stale_reason = approval_service.staleness(session, ar)
    summary = _summarize(session, [ar])[0].model_dump()
    return ApprovalDetail(
        **summary,
        patch_checksum=ar.patch_checksum,
        diff=diff,
        is_expired=is_expired,
        stale_reason=stale_reason,
        secret_warning=False,
    )


@router.get("/approvals/{approval_id}/audit", response_model=list[ApprovalAuditEntry])
def approval_audit(
    approval_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[ApprovalAuditEntry]:
    _require_approval_read(session, approval_id, user)
    events = approval_service.get_proposal_audit(session, approval_id)
    names = audit_service.display_names(session, (e.actor_id for e in events))
    entries = [ApprovalAuditEntry.model_validate(e) for e in events]
    for entry in entries:
        entry.actor_display = names.get(entry.actor_id) if entry.actor_id else None
    return entries


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def approve(
    approval_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ApprovalSummary:
    _require_approver(session, approval_id, user)
    try:
        ar = approval_service.approve(session, approval_id, decided_by=_decider(user))
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    return _summarize(session, [ar])[0]


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def reject(
    approval_id: str,
    body: Optional[RejectRequest] = None,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ApprovalSummary:
    _require_approver(session, approval_id, user)
    try:
        ar = approval_service.reject(
            session,
            approval_id,
            reason=(body.reason if body else None),
            decided_by=_decider(user),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    return _summarize(session, [ar])[0]


@router.post(
    "/approvals/{approval_id}/apply",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def apply(
    approval_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ApprovalSummary:
    _require_approver(session, approval_id, user)
    try:
        ar = approval_service.apply(session, approval_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    return _summarize(session, [ar])[0]


@router.post(
    "/approvals/{approval_id}/invalidate",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def invalidate(
    approval_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ApprovalSummary:
    _require_approver(session, approval_id, user)
    try:
        ar = approval_service.invalidate(
            session, approval_id, decided_by=_decider(user)
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
    return _summarize(session, [ar])[0]
