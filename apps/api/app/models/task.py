from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import task_priority_check_sql


class Task(SQLModel, table=True):
    __tablename__ = "task"
    # Phase 15.5: no `status` CHECK — a task may take a custom status. The set is
    # validated in the service layer (built-ins ∪ the project's status_options).
    __table_args__ = (
        CheckConstraint(task_priority_check_sql(), name="ck_task_priority"),
        Index("ix_task_project_status", "project_id", "status"),
        Index("ix_task_project_status_sort", "project_id", "status", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    phase_id: Optional[str] = Field(default=None, foreign_key="phase.id", index=True)
    stage_id: Optional[str] = Field(default=None, foreign_key="stage.id", index=True)
    # Phase 15.8: a task may be a sub-task of another task (one level deep).
    parent_task_id: Optional[str] = Field(default=None, foreign_key="task.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    status: str = Field(default="backlog")
    priority: Optional[str] = None
    sort_order: int = Field(default=0)
    due_at: Optional[str] = None
    created_at: str
    updated_at: str
