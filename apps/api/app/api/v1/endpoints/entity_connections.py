from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.entity_connection import EntityConnectionCreate, EntityConnectionRead
from app.services import entity_connection_service

router = APIRouter()


@router.get("/projects/{project_id}/connections", response_model=list[EntityConnectionRead])
def list_connections(
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[EntityConnectionRead]:
    try:
        return entity_connection_service.list_connections(
            session, project_id, entity_type, entity_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post(
    "/projects/{project_id}/connections",
    response_model=EntityConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    project_id: str,
    data: EntityConnectionCreate,
    session: Session = Depends(get_session),
) -> EntityConnectionRead:
    try:
        return entity_connection_service.create_connection(session, project_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.delete("/entity-connections/{entity_connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(
    entity_connection_id: str,
    session: Session = Depends(get_session),
) -> Response:
    if not entity_connection_service.delete_connection(session, entity_connection_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
