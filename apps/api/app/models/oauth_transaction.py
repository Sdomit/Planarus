from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class OAuthTransaction(SQLModel, table=True):
    """A server-side, one-time OAuth authorization transaction (#113).

    Replaces the old per-process HMAC ``state`` blobs used by both the login and
    the calendar flows. A transaction is created by the ``start``/``connect`` call
    and consumed exactly once by the callback:

    - only hashes are stored — ``state_hash`` (the value handed to the provider)
      and ``binder_hash`` (a cookie value that never leaves the initiating
      browser), so a leaked row cannot be replayed;
    - ``consumed_at`` is set by a conditional UPDATE, so two concurrent callbacks
      cannot both win, on SQLite and Postgres alike;
    - living in the database rather than process memory means a multi-worker or
      restarted deployment resolves the same transaction (the #120 process-local
      class of bug does not apply here).

    ``user_id`` pins link and calendar flows to the account that started them;
    ``project_id`` carries the calendar flow's target for the callback's
    re-authorization check.
    """

    __tablename__ = "oauthtransaction"
    __table_args__ = (
        Index("ix_oauthtransaction_state_hash", "state_hash", unique=True),
        Index("ix_oauthtransaction_expires_at", "expires_at"),
    )

    id: str = Field(primary_key=True)
    kind: str  # "login" | "link" | "calendar"
    provider: str
    state_hash: str
    binder_hash: str
    redirect_uri: str
    user_id: Optional[str] = Field(default=None, foreign_key="appuser.id")
    project_id: Optional[str] = None
    created_at: str
    expires_at: str
    consumed_at: Optional[str] = None
