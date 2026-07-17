from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Phase(SQLModel, table=True):
    __tablename__ = "phase"
    # Phase 15.5: no `status` CHECK — a phase may take a custom status (validated
    # in the service layer against built-ins ∪ the project's status_options).
    __table_args__ = (
        Index("ix_phase_project_sort", "project_id", "sort_order"),
        Index("ix_phase_project_status", "project_id", "status"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="planned")
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
