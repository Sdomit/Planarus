"""Doc presence / soft-lock wire types (Phase 11.2, D27)."""
from typing import Literal, Optional

from pydantic import BaseModel


class PresenceHeartbeat(BaseModel):
    mode: Literal["viewing", "editing"] = "viewing"


class PresenceEntry(BaseModel):
    """One person currently on the doc. Deliberately scalar-and-minimal:
    user_id + display_name only (both already visible to workspace members via
    the members API) — never emails or anything session-related."""

    user_id: str
    display_name: str
    mode: str
    idle_seconds: int


class PresenceView(BaseModel):
    entries: list[PresenceEntry]
    editor_user_id: Optional[str]
    you: str  # the caller's user id, so the client can tell "locked by OTHER"
    ttl_seconds: int
