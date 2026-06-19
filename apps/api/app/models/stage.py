from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import phase_status_check_sql


class Stage(SQLModel, table=True):
    """Stage within a Phase. `project_id` is denormalized for list queries."""

    __tablename__ = "stage"
    __table_args__ = (
        CheckConstraint(phase_status_check_sql(), name="ck_stage_status"),
        Index("ix_stage_phase_sort", "phase_id", "sort_order"),
        Index("ix_stage_project_sort", "project_id", "sort_order"),
        Index("ix_stage_project_status", "project_id", "status"),
    )

    id: str = Field(primary_key=True)
    phase_id: str = Field(foreign_key="phase.id", index=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="planned")
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
