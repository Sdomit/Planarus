from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import email_log_status_check_sql


class EmailLog(SQLModel, table=True):
    """Append-only record of every reminder email attempt (Phase 9).

    `sent_at` is the attempt timestamp (also set on failures). The message body
    is never stored — only recipient, subject, status, and a short error.
    """

    __tablename__ = "emaillog"
    __table_args__ = (
        CheckConstraint(email_log_status_check_sql(), name="ck_emaillog_status"),
        Index("ix_emaillog_project_sent", "project_id", "sent_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    rule_id: Optional[str] = Field(default=None, foreign_key="notificationrule.id")
    to_email: str = Field(max_length=254)
    subject: str = Field(max_length=300)
    status: str  # 'sent' | 'failed'
    error: Optional[str] = Field(default=None, max_length=500)
    sent_at: str
    created_at: str
