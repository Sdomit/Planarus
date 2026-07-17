from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import (
    comment_author_type_check_sql,
    comment_entity_type_check_sql,
    comment_status_check_sql,
)


class Comment(SQLModel, table=True):
    """A note attached to any project-scoped entity via (entity_type, entity_id).
    Editable since Phase 15.7 (body + triage `status`); `updated_at` tracks edits."""

    __tablename__ = "comment"
    __table_args__ = (
        CheckConstraint(comment_entity_type_check_sql(), name="ck_comment_entity_type"),
        CheckConstraint(comment_author_type_check_sql(), name="ck_comment_author_type"),
        CheckConstraint(comment_status_check_sql(), name="ck_comment_status"),
        Index("ix_comment_entity", "entity_type", "entity_id"),
        Index("ix_comment_project_created", "project_id", "created_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    entity_type: str
    entity_id: str
    body: str
    author_type: str = Field(default="human")
    status: str = Field(default="active")
    created_at: str
    updated_at: Optional[str] = None
