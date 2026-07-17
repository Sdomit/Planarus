from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import calendar_event_status_check_sql


class CalendarEvent(SQLModel, table=True):
    """A dated calendar event. Times are ISO-8601 strings (the repo convention).

    `all_day` events use a date-only `start_at`/`end_at` (YYYY-MM-DD); timed
    events use a full timestamp. `external_uid`/`etag` are reserved for external
    provider sync (Phase 15.12c/d) and stay NULL until a connection writes them.
    """

    __tablename__ = "calendar_event"
    __table_args__ = (
        CheckConstraint(calendar_event_status_check_sql(), name="ck_calendar_event_status"),
        Index("ix_calendar_event_project_start", "project_id", "start_at"),
        Index("ix_calendar_event_project_sort", "project_id", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    phase_id: Optional[str] = Field(default=None, foreign_key="phase.id", index=True)
    title: str = Field(max_length=200)
    description: Optional[str] = None
    location: Optional[str] = None
    status: str = Field(default="confirmed")
    start_at: str  # ISO date (all-day) or ISO datetime
    end_at: Optional[str] = None
    all_day: bool = Field(default=False)
    recurrence: str = Field(default="none")  # none|daily|weekly|monthly
    recurrence_until: Optional[str] = None  # inclusive YYYY-MM-DD; None = forever
    sort_order: int = Field(default=0)
    external_uid: Optional[str] = Field(default=None, index=True)  # reserved: sync
    etag: Optional[str] = None  # reserved: sync
    created_at: str
    updated_at: str
