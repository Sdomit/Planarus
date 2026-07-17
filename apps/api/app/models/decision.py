from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Decision(SQLModel, table=True):
    __tablename__ = "decision"
    # Phase 15.5: no `status` CHECK — custom statuses validated in the service layer.
    __table_args__ = (
        Index("ix_decision_project_status", "project_id", "status"),
        Index("ix_decision_project_created", "project_id", "created_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    title: str = Field(max_length=200)
    context: Optional[str] = None
    decision: str
    status: str = Field(default="proposed")
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
