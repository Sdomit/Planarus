import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Deliberately liberal — real address validation happens at the provider (OAuth);
# the dev provider only needs a sane, unique-ish identifier. No new dependency.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DevLoginRequest(BaseModel):
    """Password-less dev-provider login (local bootstrap + tests only)."""

    email: str = Field(min_length=3, max_length=320)
    display_name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("email must look like name@host.tld")
        return v


class UserRead(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class WorkspaceMembershipRead(BaseModel):
    """A user's role in one workspace — the caller's own membership view."""

    workspace_id: str
    role: str


class AuthMeRead(BaseModel):
    """The authenticated user plus the workspaces they belong to."""

    user: UserRead
    memberships: list[WorkspaceMembershipRead]
