from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class UserSession(SQLModel, table=True):
    """A server-side session (Phase 10.1, D20).

    Only a SHA-256 of the opaque session token is stored (``token_hash``); the raw
    token lives in the client cookie and is never persisted, logged, or returned
    after creation. Expiry and revocation are checked on every resolve; both use
    the same ISO-8601 UTC string format as ``created_at`` so plain string ``<``
    comparison is correct.
    """

    __tablename__ = "usersession"
    __table_args__ = (
        Index("ix_usersession_token_hash", "token_hash", unique=True),
        Index("ix_usersession_user_id", "user_id"),
    )

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="appuser.id")
    token_hash: str
    created_at: str
    expires_at: str
    last_seen_at: Optional[str] = None
    revoked_at: Optional[str] = None
