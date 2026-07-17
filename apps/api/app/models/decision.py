from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import decision_status_check_sql


class Decision(SQLModel, table=True):
    __tablename__ = "decision"
    __table_args__ = (
        CheckConstraint(decision_status_check_sql(), name="ck_decision_status"),
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
