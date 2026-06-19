from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import task_priority_check_sql, task_status_check_sql


class Task(SQLModel, table=True):
    __tablename__ = "task"
    __table_args__ = (
        CheckConstraint(task_status_check_sql(), name="ck_task_status"),
        CheckConstraint(task_priority_check_sql(), name="ck_task_priority"),
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_project_status_sort", "project_id", "status", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    phase_id: Optional[str] = Field(default=None, foreign_key="phase.id", index=True)
    stage_id: Optional[str] = Field(default=None, foreign_key="stage.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="backlog")
    priority: Optional[str] = None
    sort_order: int = Field(default=0)
    due_at: Optional[str] = None
    created_at: str
    updated_at: str
