from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import (
    calendar_connection_provider_check_sql,
    calendar_connection_status_check_sql,
)


class CalendarConnection(SQLModel, table=True):
    """A link between a project and an external calendar account (Google/MS).

    Access/refresh tokens are stored **encrypted** (Fernet — see token_crypto);
    the raw values never leave this row. `sync_token` is the provider's opaque
    incremental-sync cursor. Nothing here is ever returned to the client except
    the fields in `CalendarConnectionRead` (never a token).
    """

    __tablename__ = "calendar_connection"
    __table_args__ = (
        CheckConstraint(calendar_connection_provider_check_sql(), name="ck_calconn_provider"),
        CheckConstraint(calendar_connection_status_check_sql(), name="ck_calconn_status"),
        Index("ix_calendar_connection_project", "project_id"),
    )

    id: str = Field(primary_key=True)
    # No index=True: the ix_calendar_connection_project index in __table_args__
    # (migration 0017) already covers project_id. index=True would emit a second,
    # migration-less ix_calendar_connection_project_id and drift.
    project_id: str = Field(foreign_key="project.id")
    provider: str  # google | microsoft
    account_email: str
    access_token_enc: str
    refresh_token_enc: Optional[str] = None
    token_expiry: Optional[str] = None  # ISO datetime the access token expires
    scope: Optional[str] = None
    status: str = Field(default="connected")
    sync_token: Optional[str] = None  # provider incremental-sync cursor
    last_synced_at: Optional[str] = None
    created_at: str
    updated_at: str
