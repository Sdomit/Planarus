from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.comment import Comment
from app.models.project import Project
from app.schemas.comment import CommentCreate
from app.services.audit_service import create_audit_event
from app.services.entity_ref import validate_entity_ref


def list_comments(
    session: Session,
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> list[Comment]:
    stmt = select(Comment).where(Comment.project_id == project_id)
    if entity_type is not None:
        stmt = stmt.where(Comment.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(Comment.entity_id == entity_id)
    stmt = stmt.order_by(Comment.created_at, Comment.id)
    return list(session.exec(stmt).all())


def create_comment(session: Session, project_id: str, data: CommentCreate) -> Comment:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    validate_entity_ref(session, project_id, data.entity_type, data.entity_id)

    comment = Comment(
        id=new_id("cmt"),
        project_id=project_id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        body=data.body,
        author_type=data.author_type,
        created_at=now_utc(),
    )
    session.add(comment)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="comment",
        entity_id=comment.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(comment)
    return comment
