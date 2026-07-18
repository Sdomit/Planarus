import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Deliberately liberal — real address validation happens at the provider (OAuth);
# the dev provider only needs a sane, unique-ish identifier. No new dependency.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _checked_email(v: str) -> str:
    if not _EMAIL_RE.match(v.strip()):
        raise ValueError("email must look like name@host.tld")
    return v


class DevLoginRequest(BaseModel):
    """Password-less dev-provider login (local bootstrap + tests only)."""

    email: str = Field(min_length=3, max_length=320)
    display_name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _checked_email(v)


# --- P11.1: local email+password provider (D25) --------------------------------
# Length over composition (NIST 800-63B): a 10-char minimum, no character-class
# rules. The max bounds Argon2 input size; nothing truncates.
_PASSWORD_MIN = 10
_PASSWORD_MAX = 200


class PasswordRegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)
    display_name: Optional[str] = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _checked_email(v)


class PasswordLoginRequest(BaseModel):
    """No minimum on the password here — a too-short guess is just a failed
    login (generic 401), not a validation hint about the policy."""

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=_PASSWORD_MAX)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=_PASSWORD_MAX)
    new_password: str = Field(min_length=_PASSWORD_MIN, max_length=_PASSWORD_MAX)


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
