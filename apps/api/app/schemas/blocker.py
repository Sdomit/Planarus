from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import BLOCKER_STATUSES

_BLOCKER_STATUSES = frozenset(BLOCKER_STATUSES)


class BlockerCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = "open"
    task_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _BLOCKER_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_BLOCKER_STATUSES))}"
            )
        return v


class BlockerUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    task_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _BLOCKER_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_BLOCKER_STATUSES))}"
            )
        return v


class BlockerRead(BaseModel):
    id: str
    project_id: str
    task_id: Optional[str]
    title: str
    description: Optional[str]
    status: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
