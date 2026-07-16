"""Notification feed, notification rules, and email reminders (Phase 9).

Local UI only — none of this is exposed on the external API or MCP. The manual
"send reminders now" action is guarded by the local control token because it has
a side effect outside the app (an SMTP send), mirroring the approvals guard.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.core.config import settings
from app.core.security import require_local_control
from app.db.session import get_session
from app.schemas.notifications import (
    EmailLogRead,
    NotificationFeed,
    NotificationRuleCreate,
    NotificationRuleRead,
    NotificationRuleUpdate,
    ReminderSendResult,
)
from app.services import email_service, notification_service

router = APIRouter()


@router.get("/notifications", response_model=NotificationFeed)
def get_notifications(
    project_id: Optional[str] = Query(default=None),
    session: Session = Depends(get_session),
) -> NotificationFeed:
    # In hosted mode a project_id is required so the guard can scope the feed to a
    # workspace the caller belongs to — a cross-project feed would leak tenants.
    if settings.auth_enabled and project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_id is required",
        )
    try:
        return notification_service.build_feed(session, project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(
    "/projects/{project_id}/notification-rules",
    response_model=list[NotificationRuleRead],
)
def list_notification_rules(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[NotificationRuleRead]:
    return notification_service.list_rules(session, project_id)


@router.post(
    "/projects/{project_id}/notification-rules",
    response_model=NotificationRuleRead,
    status_code=status.HTTP_201_CREATED,
    # Rules configure where outbound email goes — guard the destination config
    # like api_clients, not just the send trigger.
    dependencies=[Depends(require_local_control)],
)
def create_notification_rule(
    project_id: str,
    data: NotificationRuleCreate,
    session: Session = Depends(get_session),
) -> NotificationRuleRead:
    try:
        return notification_service.create_rule(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.patch(
    "/notification-rules/{rule_id}",
    response_model=NotificationRuleRead,
    dependencies=[Depends(require_local_control)],
)
def update_notification_rule(
    rule_id: str,
    data: NotificationRuleUpdate,
    session: Session = Depends(get_session),
) -> NotificationRuleRead:
    rule = notification_service.update_rule(session, rule_id, data)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Notification rule not found"
        )
    return rule


@router.post(
    "/projects/{project_id}/reminders/send",
    response_model=ReminderSendResult,
    dependencies=[Depends(require_local_control)],
)
def send_reminders(
    project_id: str,
    session: Session = Depends(get_session),
) -> ReminderSendResult:
    try:
        return email_service.send_project_reminders(session, project_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get("/projects/{project_id}/email-log", response_model=list[EmailLogRead])
def get_email_log(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[EmailLogRead]:
    return email_service.list_email_log(session, project_id, limit=limit)
