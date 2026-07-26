from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.core.config import settings
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.doc import DocCreate, DocExportResponse, DocRead, DocSummary, DocUpdate
from app.schemas.presence import PresenceHeartbeat, PresenceView
from app.services import audit_service, doc_service
from app.services.presence_service import presence

router = APIRouter()


def _read(session: Session, doc) -> DocRead:
    """Resolve updated_by_display for a single doc (P16.3, D33)."""
    item = DocRead.model_validate(doc)
    if item.updated_by:
        item.updated_by_display = audit_service.display_names(
            session, [item.updated_by]
        ).get(item.updated_by)
    return item


@router.get("/projects/{project_id}/docs", response_model=list[DocSummary])
def list_docs(
    project_id: str,
    doc_type: Optional[str] = Query(default=None),
    doc_status: Optional[str] = Query(default=None, alias="status"),
    parent_doc_id: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    q: Optional[str] = Query(default=None, max_length=200),
    session: Session = Depends(get_session),
) -> list[DocSummary]:
    return doc_service.list_docs(
        session,
        project_id,
        doc_type=doc_type,
        status=doc_status,
        parent_doc_id=parent_doc_id,
        include_archived=include_archived,
        q=q,
    )


@router.post(
    "/projects/{project_id}/docs",
    response_model=DocRead,
    status_code=status.HTTP_201_CREATED,
)
def create_doc(
    project_id: str,
    data: DocCreate,
    session: Session = Depends(get_session),
) -> DocRead:
    try:
        return _read(session, doc_service.create_doc(session, project_id, data))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except TypeError as exc:
        # An invalid parent_doc_id (#116) — unprocessable payload, not a bad route.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/docs/{doc_id}", response_model=DocRead)
def get_doc(
    doc_id: str,
    session: Session = Depends(get_session),
) -> DocRead:
    doc = doc_service.get_doc(session, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    return _read(session, doc)


@router.patch("/docs/{doc_id}", response_model=DocRead)
def update_doc(
    doc_id: str,
    data: DocUpdate,
    session: Session = Depends(get_session),
) -> DocRead:
    try:
        return _read(session, doc_service.update_doc(session, doc_id, data))
    except TypeError as exc:
        # Not part of the app-wide vocabulary: a TypeError here means the payload
        # shape is wrong, which is a 422. Everything else — NotFoundError → 404,
        # ConflictError → 409 — is handled app-wide now (#99). This route used to
        # invert both to compensate for doc_service raising them backwards.
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.delete("/docs/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_doc(
    doc_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not doc_service.delete_doc(session, doc_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")


# --- P11.2: presence / soft-lock (D27) — polling heartbeat, in-process ---------
# On the docs router so the registry tenant_guard applies untouched: GET needs a
# viewer+ role, PUT/DELETE editor+ (a viewer can watch who's editing but never
# holds the lock), unknown doc → 404, non-member → 403. The surface 404s when
# auth is off: presence is meaningless single-user, and local mode stays
# byte-identical (the web client probes once and goes dormant).


def _presence_user(user: Optional[User]) -> User:
    """The authenticated caller, or 404 when auth (and thus presence) is off.

    ``tenant_user`` already 401'd a missing/invalid session when auth is on, so
    ``user is None`` here can only mean auth is disabled.
    """
    if not settings.auth_enabled or user is None:
        raise HTTPException(status_code=404, detail="not found")
    return user


@router.put("/docs/{doc_id}/presence", response_model=PresenceView)
def doc_presence_heartbeat(
    doc_id: str,
    data: PresenceHeartbeat,
    user: Optional[User] = Depends(tenant_user),
) -> PresenceView:
    u = _presence_user(user)
    return PresenceView(you=u.id, **presence.heartbeat(doc_id, u.id, u.display_name, data.mode))


@router.get("/docs/{doc_id}/presence", response_model=PresenceView)
def doc_presence_snapshot(
    doc_id: str,
    user: Optional[User] = Depends(tenant_user),
) -> PresenceView:
    u = _presence_user(user)
    return PresenceView(you=u.id, **presence.snapshot(doc_id))


@router.delete("/docs/{doc_id}/presence", status_code=status.HTTP_204_NO_CONTENT)
def doc_presence_leave(
    doc_id: str,
    user: Optional[User] = Depends(tenant_user),
) -> Response:
    u = _presence_user(user)
    presence.leave(doc_id, u.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/docs/{doc_id}/export-markdown", response_model=DocExportResponse)
def export_doc_markdown(
    doc_id: str,
    session: Session = Depends(get_session),
) -> DocExportResponse:
    try:
        return doc_service.export_doc_markdown(session, doc_id)
    except TypeError as exc:
        # As in update_doc: TypeError is outside the app-wide vocabulary and means
        # the project is unexportable (no project, or no folder_path), which is a
        # 422. NotFoundError → 404 and ConflictError → 409 are app-wide now (#99).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
