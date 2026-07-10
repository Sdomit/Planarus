from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import AGENT_FAMILIES, AGENT_RUN_MODES, AGENT_RUN_STATUSES

_FAMILIES = frozenset(AGENT_FAMILIES)
_MODES = frozenset(AGENT_RUN_MODES)
_STATUSES = frozenset(AGENT_RUN_STATUSES)


def _validate_family(v: str) -> str:
    if v not in _FAMILIES:
        raise ValueError(f"agent_family must be one of: {', '.join(sorted(_FAMILIES))}")
    return v


def _validate_mode(v: Optional[str]) -> Optional[str]:
    if v is not None and v not in _MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(_MODES))}")
    return v


def _validate_status(v: str) -> str:
    if v not in _STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(_STATUSES))}")
    return v


def _validate_timestamp(v: Optional[str]) -> Optional[str]:
    """Timestamps must be ISO-8601 — garbage here silently corrupts analytics."""
    if v is not None:
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("timestamp must be an ISO-8601 string")
    return v


class AgentRunCreate(BaseModel):
    agent_family: str = "unspecified"
    agent_name: Optional[str] = Field(default=None, max_length=120)
    mode: Optional[str] = None
    status: str = "started"
    summary: Optional[str] = Field(default=None, max_length=4000)
    started_at: Optional[str] = None  # defaults to now in the service
    ended_at: Optional[str] = None

    _family = field_validator("agent_family")(_validate_family)
    _mode = field_validator("mode")(_validate_mode)
    _status = field_validator("status")(_validate_status)
    _ts = field_validator("started_at", "ended_at")(_validate_timestamp)


class AgentRunUpdate(BaseModel):
    agent_family: Optional[str] = None
    agent_name: Optional[str] = Field(default=None, max_length=120)
    mode: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = Field(default=None, max_length=4000)
    ended_at: Optional[str] = None

    @field_validator("agent_family")
    @classmethod
    def _family(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _validate_family(v)

    _mode = field_validator("mode")(_validate_mode)
    _ts = field_validator("ended_at")(_validate_timestamp)

    @field_validator("status")
    @classmethod
    def _status(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _validate_status(v)


class AgentRunRead(BaseModel):
    id: str
    project_id: str
    agent_family: str
    agent_name: Optional[str]
    mode: Optional[str]
    status: str
    summary: Optional[str]
    started_at: str
    ended_at: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AgentRunAnalytics(BaseModel):
    project_id: str
    generated_at: str
    total: int
    by_family: dict[str, int]
    by_status: dict[str, int]
    by_mode: dict[str, int]
    success_rate: Optional[float]  # succeeded / (succeeded + failed); None if neither
    avg_duration_minutes: Optional[float]  # over runs with a valid started/ended pair
    last_run_at: Optional[str]
