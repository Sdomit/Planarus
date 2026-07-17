from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import TASK_PRIORITIES, TASK_STATUSES

_TASK_STATUSES = frozenset(TASK_STATUSES)
_TASK_PRIORITIES = frozenset(TASK_PRIORITIES)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = "backlog"
    priority: Optional[str] = None
    sort_order: Optional[int] = None
    due_at: Optional[str] = None
    phase_id: Optional[str] = None
    stage_id: Optional[str] = None
    parent_task_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _TASK_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_TASK_STATUSES))}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TASK_PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(sorted(_TASK_PRIORITIES))}")
        return v


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    sort_order: Optional[int] = None
    due_at: Optional[str] = None
    phase_id: Optional[str] = None
    stage_id: Optional[str] = None
    parent_task_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TASK_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_TASK_STATUSES))}")
        return v

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TASK_PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(sorted(_TASK_PRIORITIES))}")
        return v


class TaskRead(BaseModel):
    id: str
    project_id: str
    phase_id: Optional[str]
    stage_id: Optional[str]
    parent_task_id: Optional[str]
    title: str
    description: Optional[str]
    status: str
    priority: Optional[str]
    sort_order: int
    due_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
