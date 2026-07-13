from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import MILESTONE_STATUSES

_MILESTONE_STATUSES = frozenset(MILESTONE_STATUSES)


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = "planned"
    target_date: Optional[str] = None
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _MILESTONE_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_MILESTONE_STATUSES))}"
            )
        return v


class MilestoneUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    target_date: Optional[str] = None
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _MILESTONE_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_MILESTONE_STATUSES))}"
            )
        return v


class MilestoneRead(BaseModel):
    id: str
    project_id: str
    phase_id: Optional[str]
    title: str
    description: Optional[str]
    status: str
    target_date: Optional[str]
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
