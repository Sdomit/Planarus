"""Schemas for ApiClient management (Phase 7C1).

``ApiClientRead`` deliberately omits ``secret_hash`` — it is never serialized to a
response. The raw API key appears only in ``ApiClientCreated`` (returned exactly
once at creation) and is never persisted or returned again.
"""
from typing import Optional

from pydantic import BaseModel, Field


class ApiClientCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    workspace_id: str
    project_ids: list[str]
    can_read: bool = False
    can_propose: bool = False
    # User-selected expiry in days (1..365). Omitted → default 90 days. The server
    # computes the absolute expires_at; clients never supply a raw timestamp.
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class ApiClientRead(BaseModel):
    id: str
    workspace_id: str
    key_id: str
    label: str
    can_read: bool
    can_propose: bool
    project_ids: list[str]
    enabled: bool
    created_at: str
    expires_at: str
    last_used_at: Optional[str] = None
    revoked_at: Optional[str] = None


class ApiClientCreated(BaseModel):
    """One-time creation response — the only place the raw key is ever returned."""

    client: ApiClientRead
    api_key: str
    warning: str = (
        "Copy and store this API key now — it is shown only once and cannot be "
        "retrieved again."
    )
