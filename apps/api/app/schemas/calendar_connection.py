from typing import Optional

from pydantic import BaseModel


class CalendarConnectionRead(BaseModel):
    """Safe view of a connection. Deliberately omits every token/secret and the
    sync cursor — only enough to show 'Google · you@example.com · connected'."""

    id: str
    project_id: str
    provider: str
    account_email: str
    status: str
    last_synced_at: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}


class SyncResult(BaseModel):
    connection_id: str
    pushed: int
    pulled: int
    status: str
