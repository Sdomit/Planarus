from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import PHASE_STATUSES

_PHASE_STATUSES = frozenset(PHASE_STATUSES)


class PhaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = "planned"
    sort_order: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _PHASE_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_PHASE_STATUSES))}")
        return v


class PhaseUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PHASE_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_PHASE_STATUSES))}")
        return v


class PhaseRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str]
    status: str
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
