from pydantic import BaseModel, Field, field_validator

from app.core.constants import WORKSPACE_ROLES

_EMAIL_MAX = 320


def _validate_role(v: str) -> str:
    if v not in WORKSPACE_ROLES:
        raise ValueError(f"role must be one of {', '.join(WORKSPACE_ROLES)}")
    return v


class MemberAddRequest(BaseModel):
    """Add an existing user (by email) to a workspace with a role."""

    email: str = Field(min_length=3, max_length=_EMAIL_MAX)
    role: str = Field(default="viewer")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        return _validate_role(v)


class MemberRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        return _validate_role(v)


class MemberCandidate(BaseModel):
    """An account that could be added to a workspace — email + name, nothing else.

    Deliberately not MemberRead: a candidate has no membership row yet, and the
    admin flags (is_admin / is_active) are the admin plane's business, not a
    workspace owner's.
    """

    email: str
    display_name: str


class MemberRead(BaseModel):
    id: str
    workspace_id: str
    user_id: str
    email: str
    display_name: str
    role: str
    created_at: str
    updated_at: str
