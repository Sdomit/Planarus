import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import NOTIFICATION_CHANNELS, NOTIFICATION_TRIGGERS

_CHANNELS = frozenset(NOTIFICATION_CHANNELS)
_TRIGGERS = frozenset(NOTIFICATION_TRIGGERS)

# ponytail: pragmatic address shape check, not full RFC 5322 — local single-user
# tool sending to Mailpit; upgrade to a real validator with a hosted provider.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str) -> str:
    if not _EMAIL_RE.match(v):
        raise ValueError("to_email must be a valid email address")
    return v


# --- In-app notification feed (computed, no table) ---------------------------


class NotificationItem(BaseModel):
    id: str  # stable synthetic id, e.g. "task_overdue:tsk_…"
    kind: str
    severity: str  # 'action' | 'warn' | 'info'
    title: str
    detail: Optional[str]
    project_id: str
    project_title: str
    at: str


class NotificationFeed(BaseModel):
    generated_at: str
    items: list[NotificationItem]


# --- Notification rules (email reminders) ------------------------------------


class NotificationRuleCreate(BaseModel):
    channel: str = "email"
    trigger_type: str = "due_soon"
    enabled: bool = True
    to_email: str = Field(max_length=254)
    threshold_hours: int = Field(default=48, ge=1, le=720)

    @field_validator("channel")
    @classmethod
    def _channel(cls, v: str) -> str:
        if v not in _CHANNELS:
            raise ValueError(f"channel must be one of: {', '.join(sorted(_CHANNELS))}")
        # ponytail: only email rules do anything today (the in-app feed and
        # desktop alerts are always-on). Reject the inert channels rather than
        # store dead rows; widen when a second channel actually exists.
        if v != "email":
            raise ValueError("only the 'email' channel is supported today")
        return v

    @field_validator("trigger_type")
    @classmethod
    def _trigger(cls, v: str) -> str:
        if v not in _TRIGGERS:
            raise ValueError(
                f"trigger_type must be one of: {', '.join(sorted(_TRIGGERS))}"
            )
        return v

    _to_email = field_validator("to_email")(_validate_email)


class NotificationRuleUpdate(BaseModel):
    trigger_type: Optional[str] = None
    enabled: Optional[bool] = None
    to_email: Optional[str] = Field(default=None, max_length=254)
    threshold_hours: Optional[int] = Field(default=None, ge=1, le=720)

    @field_validator("trigger_type")
    @classmethod
    def _trigger(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _TRIGGERS:
            raise ValueError(
                f"trigger_type must be one of: {', '.join(sorted(_TRIGGERS))}"
            )
        return v

    @field_validator("to_email")
    @classmethod
    def _to_email(cls, v: Optional[str]) -> Optional[str]:
        return v if v is None else _validate_email(v)


class NotificationRuleRead(BaseModel):
    id: str
    project_id: str
    channel: str
    trigger_type: str
    enabled: bool
    to_email: str
    threshold_hours: int
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# --- Email log + manual send --------------------------------------------------


class EmailLogRead(BaseModel):
    id: str
    project_id: str
    rule_id: Optional[str]
    to_email: str
    subject: str
    status: str
    error: Optional[str]
    sent_at: str
    created_at: str

    model_config = {"from_attributes": True}


class ReminderOutcome(BaseModel):
    rule_id: str
    status: str  # 'sent' | 'skipped' | 'failed'
    reason: Optional[str] = None
    email_log_id: Optional[str] = None


class ReminderSendResult(BaseModel):
    project_id: str
    sent: int
    skipped: int
    failed: int
    outcomes: list[ReminderOutcome]
