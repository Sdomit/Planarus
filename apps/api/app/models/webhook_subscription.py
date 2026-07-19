from typing import Optional

from sqlmodel import Field, SQLModel


class WebhookSubscription(SQLModel, table=True):
    """An outbound webhook: signed POSTs to ``target_url`` when matching project
    events occur (P17.3). The HMAC signing secret is stored Fernet-encrypted in
    ``secret_enc`` (see webhook_crypto) and never returned after creation.

    ``event_kinds_json`` / ``project_ids_json`` are JSON arrays; an empty array
    means "all eligible kinds" / "all projects in the workspace". Deliveries are
    read + notify only — a webhook never approves or applies. Auto-disabled after
    too many consecutive failures (``enabled`` flips False; ``failure_count``
    freezes and ``disabled_at`` is stamped).
    """

    __tablename__ = "webhook_subscription"

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    target_url: str
    secret_enc: str
    event_kinds_json: str = Field(default="[]")
    project_ids_json: str = Field(default="[]")
    format: str = Field(default="json")  # json | slack | discord (json only in 17.3a)
    enabled: bool = Field(default=True)
    failure_count: int = Field(default=0)
    created_at: str
    disabled_at: Optional[str] = None
