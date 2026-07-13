from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class ChecklistItem(SQLModel, table=True):
    """A subtask/checkbox under a Task. project_id is not stored — it is derived
    from the parent task when an audit event needs it (see checklist_service)."""

    __tablename__ = "checklistitem"
    __table_args__ = (
        Index("ix_checklistitem_task_sort", "task_id", "sort_order"),
    )

    id: str = Field(primary_key=True)
    task_id: str = Field(foreign_key="task.id", index=True)
    label: str = Field(max_length=300)
    done: bool = Field(default=False)
    sort_order: int = Field(default=0)
    created_at: str
    updated_at: str
