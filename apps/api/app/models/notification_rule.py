from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import (
    notification_channel_check_sql,
    notification_trigger_check_sql,
)


class NotificationRule(SQLModel, table=True):
    """When/how to notify for one project (Phase 9).

    Only `channel='email'` rules drive sends today; the in-app feed and desktop
    notifications are always-on client concerns and need no rule row.
    Sending is manual ("send now") — there is no scheduler.
    """

    __tablename__ = "notificationrule"
    __table_args__ = (
        CheckConstraint(
            notification_channel_check_sql(), name="ck_notificationrule_channel"
        ),
        CheckConstraint(
            notification_trigger_check_sql(), name="ck_notificationrule_trigger"
        ),
        CheckConstraint("threshold_hours > 0", name="ck_notificationrule_threshold"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    channel: str = Field(default="email")
    trigger_type: str = Field(default="due_soon")
    enabled: bool = Field(default=True)
    to_email: str = Field(max_length=254)
    threshold_hours: int = Field(default=48)
    created_at: str
    updated_at: str
