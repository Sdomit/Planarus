from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import CALENDAR_EVENT_STATUSES

_CALENDAR_EVENT_STATUSES = frozenset(CALENDAR_EVENT_STATUSES)


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    location: Optional[str] = None
    status: str = "confirmed"
    start_at: str = Field(min_length=1)
    end_at: Optional[str] = None
    all_day: bool = False
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _CALENDAR_EVENT_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_CALENDAR_EVENT_STATUSES))}"
            )
        return v


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None
    start_at: Optional[str] = Field(default=None, min_length=1)
    end_at: Optional[str] = None
    all_day: Optional[bool] = None
    phase_id: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _CALENDAR_EVENT_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_CALENDAR_EVENT_STATUSES))}"
            )
        return v


class CalendarEventRead(BaseModel):
    id: str
    project_id: str
    phase_id: Optional[str]
    title: str
    description: Optional[str]
    location: Optional[str]
    status: str
    start_at: str
    end_at: Optional[str]
    all_day: bool
    sort_order: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CalendarItem(BaseModel):
    """A normalized entry in the aggregated calendar feed. `source` says which
    entity it came from; `ref_id` is that entity's id (== id for events)."""

    id: str
    source: str  # 'event' | 'milestone' | 'task'
    ref_id: str
    title: str
    start_at: str
    end_at: Optional[str] = None
    all_day: bool
    status: Optional[str] = None
    phase_id: Optional[str] = None


class ProjectCalendar(BaseModel):
    project_id: str
    generated_at: str
    items: list[CalendarItem]
