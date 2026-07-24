from typing import Optional

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import (
    DEFAULT_STATUS_CATEGORY,
    status_category_check_sql,
    status_option_entity_type_check_sql,
)


class StatusOption(SQLModel, table=True):
    """A user-defined status (board column) for an entity kind within a project
    (Phase 15.5). Built-in canonical statuses are NOT stored here — this table
    holds only the custom ones. `key` is the value written to the entity's
    `status` column; it is unique per (project, entity_type)."""

    __tablename__ = "status_option"
    __table_args__ = (
        CheckConstraint(status_option_entity_type_check_sql(), name="ck_status_option_entity_type"),
        CheckConstraint(status_category_check_sql(), name="ck_status_option_category"),
        UniqueConstraint("project_id", "entity_type", "key", name="uq_status_option_key"),
        Index("ix_status_option_project_entity", "project_id", "entity_type", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    entity_type: str
    key: str  # slug written to the entity's status column
    label: str = Field(max_length=60)
    # #88: open | done | canceled — what this column means to the roadmap, the
    # notification bell and the agent brief. Defaults to `open`, which is how
    # every custom status behaved before the column existed.
    category: str = Field(default=DEFAULT_STATUS_CATEGORY)
    color: Optional[str] = None
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
