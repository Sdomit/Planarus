from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DECISION_STATUSES

_DECISION_STATUSES = frozenset(DECISION_STATUSES)


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    context: Optional[str] = None
    decision: str = Field(min_length=1)
    status: str = "proposed"

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _DECISION_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_DECISION_STATUSES))}"
            )
        return v


class DecisionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    context: Optional[str] = None
    decision: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DECISION_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_DECISION_STATUSES))}"
            )
        return v


class DecisionRead(BaseModel):
    id: str
    project_id: str
    title: str
    context: Optional[str]
    decision: str
    status: str
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
