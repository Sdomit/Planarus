from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import (
    comment_author_type_check_sql,
    comment_entity_type_check_sql,
)


class Comment(SQLModel, table=True):
    """Append-only note attached to any project-scoped entity via
    (entity_type, entity_id). No updated_at — comments are immutable once made."""

    __tablename__ = "comment"
    __table_args__ = (
        CheckConstraint(comment_entity_type_check_sql(), name="ck_comment_entity_type"),
        CheckConstraint(comment_author_type_check_sql(), name="ck_comment_author_type"),
        Index("ix_comment_entity", "entity_type", "entity_id"),
        Index("ix_comment_project_created", "project_id", "created_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    entity_type: str
    entity_id: str
    body: str
    author_type: str = Field(default="human")
    created_at: str
