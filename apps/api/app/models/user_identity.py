from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import auth_provider_check_sql


class UserIdentity(SQLModel, table=True):
    """One (provider, subject) login linked to a ``User`` (Phase 10.1).

    ``provider_subject`` is the stable identifier the provider asserts — the OAuth
    ``sub`` claim, or the normalized email for the ``dev``/``password`` providers.
    Unique per provider so two users can never claim the same external identity.

    ``password_hash`` (P11.1) holds the Argon2id verifier for ``password``
    provider rows only (NULL for every other provider). It never leaves the DB:
    no schema exposes it and it is never logged.
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
    password_hash: str | None = Field(default=None)
    created_at: str
