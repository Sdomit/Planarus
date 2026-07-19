from typing import Optional

from pydantic import BaseModel


class WebhookCreate(BaseModel):
    workspace_id: str
    target_url: str
    event_kinds: list[str] = []  # empty → all eligible kinds
    project_ids: list[str] = []  # empty → all projects in the workspace
    format: str = "json"


class WebhookRead(BaseModel):
    id: str
    workspace_id: str
    target_url: str
    event_kinds: list[str]
    project_ids: list[str]
    format: str
    enabled: bool
    failure_count: int
    created_at: str
    disabled_at: Optional[str] = None


class WebhookCreated(BaseModel):
    """Create response — the signing secret is shown exactly once."""

    subscription: WebhookRead
    secret: str


class WebhookDeliveryRead(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    subscription_id: str
    event_kind: str
    event_id: Optional[str] = None
    status: str
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempt: int
    created_at: str
    delivered_at: Optional[str] = None
