"""Phase 6A Context Pack Builder endpoints — read/generate only.

No external AI API call, no execution, no write-to-project surface. Preview is
side-effect free: it neither persists the pack nor writes an AuditEvent.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.context_pack import (
    ContextPackPreviewRequest,
    ContextPackPreviewResponse,
    ContextPackSourcesResponse,
    ProfilesResponse,
)
from app.services import context_pack_service, project_service

router = APIRouter()


@router.get("/context-pack/profiles", response_model=ProfilesResponse)
def get_context_pack_profiles() -> ProfilesResponse:
    """Static, versioned built-in prompt profiles + target tools + budgets."""
    return context_pack_service.list_profiles()


@router.get(
    "/projects/{project_id}/context-pack/sources",
    response_model=ContextPackSourcesResponse,
)
def get_context_pack_sources(
    project_id: str,
    session: Session = Depends(get_session),
) -> ContextPackSourcesResponse:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return context_pack_service.build_sources(session, project)


@router.post(
    "/projects/{project_id}/context-pack/preview",
    response_model=ContextPackPreviewResponse,
)
def preview_context_pack(
    project_id: str,
    request: ContextPackPreviewRequest,
    session: Session = Depends(get_session),
) -> ContextPackPreviewResponse:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    try:
        return context_pack_service.generate_preview(session, project, request)
    except context_pack_service.DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )
    except context_pack_service.PackTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
