import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Phase 15.5: decision statuses allow custom values — slug shape only here; the
# concrete per-project set is validated in the service layer.
_STATUS_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _validate_status_slug(v: Optional[str]) -> Optional[str]:
    if v is not None and not _STATUS_SLUG.match(v):
        raise ValueError("status must be a lowercase slug (letters, digits, underscore)")
    return v


class DecisionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    context: Optional[str] = None
    decision: str = Field(min_length=1)
    status: str = "proposed"
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_status_slug(v) or v


class DecisionUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    context: Optional[str] = None
    decision: Optional[str] = Field(default=None, min_length=1)
    status: Optional[str] = None
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        return _validate_status_slug(v)


class DecisionRead(BaseModel):
    id: str
    project_id: str
    phase_id: Optional[str]
    title: str
    context: Optional[str]
    decision: str
    status: str
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
