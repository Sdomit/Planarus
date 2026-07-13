from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.comment import CommentCreate, CommentRead
from app.services import comment_service

router = APIRouter()


@router.get("/projects/{project_id}/comments", response_model=list[CommentRead])
def list_comments(
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[CommentRead]:
    return comment_service.list_comments(session, project_id, entity_type, entity_id)


@router.post(
    "/projects/{project_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_comment(
    project_id: str,
    data: CommentCreate,
    session: Session = Depends(get_session),
) -> CommentRead:
    try:
        return comment_service.create_comment(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
