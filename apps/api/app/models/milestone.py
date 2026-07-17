from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Milestone(SQLModel, table=True):
    __tablename__ = "milestone"
    # Phase 15.5: no `status` CHECK — custom statuses validated in the service layer.
    __table_args__ = (
        Index("ix_milestone_project_status", "project_id", "status"),
        Index("ix_milestone_project_sort", "project_id", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    phase_id: Optional[str] = Field(default=None, foreign_key="phase.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="planned")
    target_date: Optional[str] = None  # ISO date (YYYY-MM-DD) or empty
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
