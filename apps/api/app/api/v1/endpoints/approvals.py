"""Local human approval API (Phase 7A).

Read endpoints (list/detail/audit) are local-read-only. State-changing endpoints
(approve/reject/apply/invalidate) require the in-memory local control token AND an
allowed Origin via ``require_local_control``. There is deliberately NO
proposal-creation endpoint in Phase 7A — proposals are created only through the
``approval_service`` internal seam.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.core.security import (
    get_local_control_token,
    origin_allowed,
    require_local_control,
)
from app.db.session import get_session
from app.schemas.approval import (
    ApprovalAuditEntry,
    ApprovalDetail,
    ApprovalSummary,
    LocalSessionResponse,
    RejectRequest,
)
from app.services import approval_service

router = APIRouter()


@router.get("/local-session", response_model=LocalSessionResponse)
def local_session(request: Request) -> LocalSessionResponse:
    """Hand the per-process local control token to the local UI.

    A present-but-foreign Origin is rejected; the global CORS policy additionally
    prevents a browser from reading this response cross-site.
    """
    if not origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="origin not allowed")
    return LocalSessionResponse(token=get_local_control_token())


@router.get("/approvals", response_model=list[ApprovalSummary])
def list_approvals(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[ApprovalSummary]:
    return approval_service.list_approvals(session, project_id=project_id, status=status)


@router.get("/approvals/{approval_id}", response_model=ApprovalDetail)
def get_approval(
    approval_id: str, session: Session = Depends(get_session)
) -> ApprovalDetail:
    ar = approval_service.get_approval(session, approval_id)
    if ar is None:
        raise HTTPException(status_code=404, detail="approval not found")
    diff = approval_service.build_diff(session, ar)
    is_expired, stale_reason = approval_service.staleness(session, ar)
    summary = ApprovalSummary.model_validate(ar).model_dump()
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
    approval_id: str, session: Session = Depends(get_session)
) -> list[ApprovalAuditEntry]:
    if approval_service.get_approval(session, approval_id) is None:
        raise HTTPException(status_code=404, detail="approval not found")
    return approval_service.get_proposal_audit(session, approval_id)


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def approve(
    approval_id: str, session: Session = Depends(get_session)
) -> ApprovalSummary:
    try:
        return approval_service.approve(session, approval_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def reject(
    approval_id: str,
    body: Optional[RejectRequest] = None,
    session: Session = Depends(get_session),
) -> ApprovalSummary:
    try:
        return approval_service.reject(
            session, approval_id, reason=(body.reason if body else None)
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post(
    "/approvals/{approval_id}/apply",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def apply(
    approval_id: str, session: Session = Depends(get_session)
) -> ApprovalSummary:
    try:
        return approval_service.apply(session, approval_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")


@router.post(
    "/approvals/{approval_id}/invalidate",
    response_model=ApprovalSummary,
    dependencies=[Depends(require_local_control)],
)
def invalidate(
    approval_id: str, session: Session = Depends(get_session)
) -> ApprovalSummary:
    try:
        return approval_service.invalidate(session, approval_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="approval not found")
