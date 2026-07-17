from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class Todo(SQLModel, table=True):
    """A lightweight, project-scoped sidebar todo. Self-nesting via ``parent_id``
    (arbitrary depth — sub, sub-sub, …). Deliberately NOT audited: it is a personal
    scratchpad, not approval-gated canonical planning state, so toggling a checkbox
    should not flood the audit/timeline."""

    __tablename__ = "todo"
    __table_args__ = (
        Index("ix_todo_project_sort", "project_id", "sort_order"),
        Index("ix_todo_parent_id", "parent_id"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    parent_id: Optional[str] = Field(default=None, foreign_key="todo.id")
    label: str = Field(max_length=500)
    done: bool = Field(default=False)
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
