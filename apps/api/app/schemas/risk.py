from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import RISK_SEVERITIES, RISK_STATUSES

_RISK_STATUSES = frozenset(RISK_STATUSES)
_RISK_SEVERITIES = frozenset(RISK_SEVERITIES)


class RiskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    severity: str
    status: str = "open"
    mitigation: Optional[str] = None

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
        if v not in _RISK_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_RISK_STATUSES))}"
            )
        return v


class RiskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    severity: Optional[str] = None
    status: Optional[str] = None
    mitigation: Optional[str] = None

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
        if v is not None and v not in _RISK_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_RISK_STATUSES))}"
            )
        return v


class RiskRead(BaseModel):
    id: str
    project_id: str
    title: str
    description: Optional[str]
    severity: str
    status: str
    mitigation: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
