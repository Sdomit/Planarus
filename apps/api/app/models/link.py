from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import link_entity_type_check_sql


class Link(SQLModel, table=True):
    """Append-only URL reference attached to any project-scoped entity via
    (entity_type, entity_id). ponytail: url + optional title only; link_type
    taxonomy + notes (03-data-model.md) deferred until a consumer needs them."""

    __tablename__ = "link"
    __table_args__ = (
        CheckConstraint(link_entity_type_check_sql(), name="ck_link_entity_type"),
        Index("ix_link_entity", "entity_type", "entity_id"),
        Index("ix_link_project_created", "project_id", "created_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    entity_type: str
    entity_id: str
    url: str = Field(max_length=2000)
    title: Optional[str] = Field(default=None, max_length=300)
    created_at: str
