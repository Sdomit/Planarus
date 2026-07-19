"""Admin-plane wire types (Phase 16.1, D29/D31).

The temp password appears only in ``AdminUserCreated`` / ``AdminPasswordReset``
— shown once, stored only as an Argon2id hash, never logged or audited.
"""
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import WorkspaceMembershipRead, _checked_email


class AdminUserRead(BaseModel):
    """One roster row: the account plus where it belongs and when it was last
    seen (max over its sessions; None = never signed in)."""

    id: str
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: str
    last_seen_at: Optional[str] = None
    memberships: list[WorkspaceMembershipRead] = []


class AdminUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _checked_email(v)


class AdminUserCreated(BaseModel):
    user: AdminUserRead
    temp_password: str  # one-time display; the user must change it on sign-in


class AdminPasswordReset(BaseModel):
    temp_password: str  # one-time display; all existing sessions are revoked


class AdminUserPatch(BaseModel):
    model_config = {"extra": "forbid"}

    is_admin: bool
