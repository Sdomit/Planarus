import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import TASK_PRIORITIES

_TASK_PRIORITIES = frozenset(TASK_PRIORITIES)
# Phase 15.5: statuses are no longer a fixed enum (custom statuses are allowed),
# but must be a slug — the concrete set is checked in the service layer against
# the project's built-in ∪ custom options.
_STATUS_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _validate_status_slug(v: Optional[str]) -> Optional[str]:
    if v is not None and not _STATUS_SLUG.match(v):
        raise ValueError("status must be a lowercase slug (letters, digits, underscore)")
    return v


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
    assignee_id: Optional[str] = None  # P16.3 (D33): a team member; None in local mode

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_status_slug(v) or v

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
    # P16.3 (D33): send null to unassign. exclude_unset keeps "not sent" ≠ "cleared".
    assignee_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        return _validate_status_slug(v)

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
    assignee_id: Optional[str] = None
    # P16.3 (D33): resolved at read time; None in local mode or when unassigned.
    assignee_display: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
