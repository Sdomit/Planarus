from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from app.core.config import settings
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.doc import DocCreate, DocExportResponse, DocRead, DocSummary, DocUpdate
from app.schemas.presence import PresenceHeartbeat, PresenceView
from app.services import doc_service
from app.services.presence_service import presence

router = APIRouter()


@router.get("/projects/{project_id}/docs", response_model=list[DocSummary])
def list_docs(
    project_id: str,
    doc_type: Optional[str] = Query(default=None),
    doc_status: Optional[str] = Query(default=None, alias="status"),
    parent_doc_id: Optional[str] = Query(default=None),
    include_archived: bool = Query(default=False),
    session: Session = Depends(get_session),
) -> list[DocSummary]:
    return doc_service.list_docs(
        session,
        project_id,
        doc_type=doc_type,
        status=doc_status,
        parent_doc_id=parent_doc_id,
        include_archived=include_archived,
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
        return doc_service.create_doc(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/docs/{doc_id}", response_model=DocRead)
def get_doc(
    doc_id: str,
    session: Session = Depends(get_session),
) -> DocRead:
    doc = doc_service.get_doc(session, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    return doc


@router.patch("/docs/{doc_id}", response_model=DocRead)
def update_doc(
    doc_id: str,
    data: DocUpdate,
    session: Session = Depends(get_session),
) -> DocRead:
    try:
        return doc_service.update_doc(session, doc_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except TypeError as exc:
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
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except TypeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
