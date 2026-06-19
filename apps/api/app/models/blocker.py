from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import blocker_status_check_sql


class Blocker(SQLModel, table=True):
    __tablename__ = "blocker"
    __table_args__ = (
        CheckConstraint(blocker_status_check_sql(), name="ck_blocker_status"),
        Index("ix_blocker_project_status", "project_id", "status"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    task_id: Optional[str] = Field(default=None, foreign_key="task.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="open")
    created_at: str
    updated_at: str
