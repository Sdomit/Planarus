from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.services import audit_service, comment_service

router = APIRouter()


def _read(session: Session, comments) -> list[CommentRead]:
    """Resolve author_display for a batch of comments (P16.3, D33)."""
    items = [CommentRead.model_validate(c) for c in comments]
    names = audit_service.display_names(session, (i.author_id for i in items))
    for i in items:
        i.author_display = names.get(i.author_id) if i.author_id else None
    return items


@router.get("/projects/{project_id}/comments", response_model=list[CommentRead])
def list_comments(
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    session: Session = Depends(get_session),
) -> list[CommentRead]:
    return _read(
        session,
        comment_service.list_comments(session, project_id, entity_type, entity_id),
    )


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
        return _read(session, [comment_service.create_comment(session, project_id, data)])[0]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch("/comments/{comment_id}", response_model=CommentRead)
def update_comment(
    comment_id: str,
    data: CommentUpdate,
    session: Session = Depends(get_session),
) -> CommentRead:
    comment = comment_service.update_comment(session, comment_id, data)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return _read(session, [comment])[0]


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not comment_service.delete_comment(session, comment_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
