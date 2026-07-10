"""In-app notification feed (computed, no table) + notification-rule CRUD.

The feed is derived on demand from canonical state — pending approvals, due and
overdue tasks, open blockers. Nothing is stored, so there is no read/unread
state to migrate and the feed can never drift from the DB.
"""
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc, now_utc_plus_hours
from app.models.approval_request import ApprovalRequest
from app.models.blocker import Blocker
from app.models.notification_rule import NotificationRule
from app.models.project import Project
from app.models.task import Task
from app.schemas.notifications import (
    NotificationFeed,
    NotificationItem,
    NotificationRuleCreate,
    NotificationRuleUpdate,
)
from app.services.audit_service import create_audit_event

# Fixed feed window for "due soon" (email rules carry their own threshold).
DUE_SOON_WINDOW_HOURS = 48

_TASK_OPEN = ("done", "canceled")  # statuses excluded from due reminders
_SEVERITY_RANK = {"action": 0, "warn": 1, "info": 2}


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string; a naive value is assumed UTC; garbage → None.

    Task.due_at is free text (also settable through approved agent proposals),
    so due-date math must parse — lexicographic comparison would misplace any
    non-UTC offset or non-ISO value.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def due_task_buckets(
    session: Session, project_id: str, window_hours: float
) -> tuple[list[Task], list[Task]]:
    """(overdue, due_soon) open tasks with a parseable due date, ordered by due_at.

    Tasks whose due_at cannot be parsed are excluded — never guessed at.
    """
    now = _parse_ts(now_utc())
    horizon = _parse_ts(now_utc_plus_hours(window_hours))
    assert now is not None and horizon is not None
    tasks = session.exec(
        select(Task)
        .where(Task.project_id == project_id)
        .where(Task.due_at.is_not(None))  # type: ignore[union-attr]
        .where(Task.status.not_in(_TASK_OPEN))  # type: ignore[attr-defined]
        .order_by(Task.due_at)
    ).all()
    overdue: list[Task] = []
    due_soon: list[Task] = []
    for t in tasks:
        due = _parse_ts(t.due_at)
        if due is None:
            continue
        if due < now:
            overdue.append(t)
        elif due <= horizon:
            due_soon.append(t)
    return overdue, due_soon


def _project_items(session: Session, project: Project) -> list[NotificationItem]:
    items: list[NotificationItem] = []
    now = now_utc()
    # Proposals live 24h (Phase 7A); flag the last 6h as "expiring soon".
    expiring_horizon = now_utc_plus_hours(6)

    def add(kind: str, severity: str, title: str, detail: Optional[str], entity_id: str, at: str) -> None:
        items.append(
            NotificationItem(
                id=f"{kind}:{entity_id}",
                kind=kind,
                severity=severity,
                title=title,
                detail=detail,
                project_id=project.id,
                project_title=project.title,
                at=at,
            )
        )

    approvals = session.exec(
        select(ApprovalRequest)
        .where(ApprovalRequest.project_id == project.id)
        .where(ApprovalRequest.status == "pending")
    ).all()
    for ap in approvals:
        if ap.expires_at <= now:
            continue  # stale — cannot be applied anymore
        if ap.expires_at <= expiring_horizon:
            add(
                "approval_expiring",
                "action",
                f"Proposal expiring soon: {ap.action_type}",
                f"origin {ap.origin}; expires {ap.expires_at}",
                ap.id,
                ap.created_at,
            )
        else:
            add(
                "approval_pending",
                "action",
                f"Proposal awaiting review: {ap.action_type}",
                f"origin {ap.origin}",
                ap.id,
                ap.created_at,
            )

    overdue, due_soon = due_task_buckets(session, project.id, DUE_SOON_WINDOW_HOURS)
    for t in overdue:
        add("task_overdue", "warn", f"Task overdue: {t.title}", f"due {t.due_at}", t.id, t.due_at or now)
    for t in due_soon:
        add("task_due_soon", "info", f"Task due soon: {t.title}", f"due {t.due_at}", t.id, t.due_at or now)

    blockers = session.exec(
        select(Blocker)
        .where(Blocker.project_id == project.id)
        .where(Blocker.status == "open")
    ).all()
    for b in blockers:
        add("blocker_open", "warn", f"Open blocker: {b.title}", b.description, b.id, b.created_at)

    return items


def build_feed(session: Session, project_id: Optional[str] = None) -> NotificationFeed:
    if project_id is not None:
        project = session.get(Project, project_id)
        if project is None:
            raise ValueError(f"project '{project_id}' not found")
        projects = [project]
    else:
        projects = list(
            session.exec(
                select(Project).where(Project.archived_at.is_(None))  # type: ignore[union-attr]
            ).all()
        )

    items: list[NotificationItem] = []
    for project in projects:
        items.extend(_project_items(session, project))

    # Newest first within severity; actions before warnings before info.
    items.sort(key=lambda i: i.at, reverse=True)
    items.sort(key=lambda i: _SEVERITY_RANK.get(i.severity, 9))
    return NotificationFeed(generated_at=now_utc(), items=items)


# --- Notification rules (email reminders) ------------------------------------


def list_rules(session: Session, project_id: str) -> list[NotificationRule]:
    stmt = (
        select(NotificationRule)
        .where(NotificationRule.project_id == project_id)
        .order_by(NotificationRule.created_at, NotificationRule.id)
    )
    return list(session.exec(stmt).all())


def create_rule(
    session: Session, project_id: str, data: NotificationRuleCreate
) -> NotificationRule:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    now = now_utc()
    rule = NotificationRule(
        id=new_id("nrl"),
        project_id=project_id,
        channel=data.channel,
        trigger_type=data.trigger_type,
        enabled=data.enabled,
        to_email=data.to_email,
        threshold_hours=data.threshold_hours,
        created_at=now,
        updated_at=now,
    )
    session.add(rule)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="notification_rule",
        entity_id=rule.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(rule)
    return rule


def update_rule(
    session: Session, rule_id: str, data: NotificationRuleUpdate
) -> Optional[NotificationRule]:
    rule = session.get(NotificationRule, rule_id)
    if rule is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(rule, key, value)
    rule.updated_at = now_utc()
    session.add(rule)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="notification_rule",
        entity_id=rule_id,
        project_id=rule.project_id,
    )
    session.commit()
    session.refresh(rule)
    return rule
