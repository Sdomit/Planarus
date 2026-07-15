from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import auth_provider_check_sql


class UserIdentity(SQLModel, table=True):
    """One (provider, subject) login linked to a ``User`` (Phase 10.1).

    ``provider_subject`` is the stable identifier the provider asserts — the OAuth
    ``sub`` claim, or the normalized email for the ``dev`` provider. Unique per
    provider so two users can never claim the same external identity.
    """

    __tablename__ = "useridentity"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_useridentity_provider_subject"
        ),
        CheckConstraint(auth_provider_check_sql(), name="ck_useridentity_provider"),
        Index("ix_useridentity_user_id", "user_id"),
    )

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="appuser.id")
    provider: str
    provider_subject: str = Field(max_length=320)
    created_at: str
