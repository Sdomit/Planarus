from typing import Optional

from sqlmodel import Field, SQLModel


class WebhookDelivery(SQLModel, table=True):
    """One attempt to deliver an event to a subscription (P17.3).

    ``request_body`` is the exact signed JSON envelope that was (or will be) sent,
    kept verbatim so a delivery can be re-sent identically on redeliver.
    ``status``: pending | delivered | failed.
    """

    __tablename__ = "webhook_delivery"

    id: str = Field(primary_key=True)
    subscription_id: str = Field(foreign_key="webhook_subscription.id", index=True)
    event_kind: str
    event_id: Optional[str] = None
    request_body: str
    status: str = Field(default="pending")
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempt: int = Field(default=1)
    created_at: str
    delivered_at: Optional[str] = None
