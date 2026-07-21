import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import RISK_SEVERITIES

_RISK_SEVERITIES = frozenset(RISK_SEVERITIES)
# Phase 15.5: risk statuses allow custom values — slug shape only here; the
# concrete per-project set is validated in the service layer. Severity stays fixed.
_STATUS_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def _validate_status_slug(v: Optional[str]) -> Optional[str]:
    if v is not None and not _STATUS_SLUG.match(v):
        raise ValueError("status must be a lowercase slug (letters, digits, underscore)")
    return v


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    severity: str
    status: str = "open"
    mitigation: Optional[str] = None
    phase_id: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in _RISK_SEVERITIES:
            raise ValueError(
                f"severity must be one of: {', '.join(sorted(_RISK_SEVERITIES))}"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_status_slug(v) or v


class RiskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    mitigation: Optional[str] = None
    phase_id: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _RISK_SEVERITIES:
            raise ValueError(
                f"severity must be one of: {', '.join(sorted(_RISK_SEVERITIES))}"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        return _validate_status_slug(v)


class RiskRead(BaseModel):
    id: str
    project_id: str
    phase_id: Optional[str]
    title: str
    description: Optional[str]
    severity: str
    status: str
    mitigation: Optional[str]
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
