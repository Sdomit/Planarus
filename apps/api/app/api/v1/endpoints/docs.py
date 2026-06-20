from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.doc import DocCreate, DocExportResponse, DocRead, DocSummary, DocUpdate
from app.services import doc_service

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
