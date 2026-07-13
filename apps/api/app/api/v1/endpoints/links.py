from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.link import LinkCreate, LinkRead
from app.services import link_service

router = APIRouter()


@router.get("/projects/{project_id}/links", response_model=list[LinkRead])
def list_links(
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[LinkRead]:
    return link_service.list_links(session, project_id, entity_type, entity_id)


@router.post(
    "/projects/{project_id}/links",
    response_model=LinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_link(
    project_id: str,
    data: LinkCreate,
    session: Session = Depends(get_session),
) -> LinkRead:
    try:
        return link_service.create_link(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
