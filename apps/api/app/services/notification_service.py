"""In-app notification feed (computed, no table) + notification-rule CRUD.

The feed is derived on demand from canonical state — pending approvals, due and
overdue tasks, open blockers. Nothing is stored, so there is no read/unread
state to migrate and the feed can never drift from the DB.
"""
from datetime import datetime, timezone
from typing import Iterable, Optional

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
from app.services import status_option_service
from app.services.audit_service import create_audit_event

# Fixed feed window for "due soon" (email rules carry their own threshold).
DUE_SOON_WINDOW_HOURS = 48

# #88: which statuses are excluded from due-date nagging is now a per-project
# question — a custom column marked done or canceled is finished work, and
# nagging about it forever was the bug.
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


def _bucket_by_due(
    tasks: Iterable[Task], window_hours: float
) -> tuple[list[Task], list[Task]]:
    """Split already-fetched open, dated tasks into (overdue, due_soon).

    Kept separate from the query so the per-project and batched callers share one
    definition of the window. Tasks whose due_at cannot be parsed are excluded —
    never guessed at.
    """
    now = _parse_ts(now_utc())
    horizon = _parse_ts(now_utc_plus_hours(window_hours))
    assert now is not None and horizon is not None
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


def due_task_buckets(
    session: Session, project_id: str, window_hours: float
) -> tuple[list[Task], list[Task]]:
    """(overdue, due_soon) open tasks with a parseable due date, ordered by due_at.

    Tasks whose due_at cannot be parsed are excluded — never guessed at.
    """
    closed = status_option_service.status_keys_in(
        session, project_id, "task", "done", "canceled"
    )
    tasks = session.exec(
        select(Task)
        .where(Task.project_id == project_id)
        .where(Task.due_at.is_not(None))  # type: ignore[union-attr]
        .where(Task.status.not_in(closed))  # type: ignore[attr-defined]
        .order_by(Task.due_at)
    ).all()
    return _bucket_by_due(tasks, window_hours)


def _project_items(
    project: Project,
    approvals: list[ApprovalRequest],
    tasks: list[Task],
    blockers: list[Blocker],
) -> list[NotificationItem]:
    """Render one project's rows from state already fetched by ``build_feed``.

    #103: this used to run its own three queries, so the whole-workspace feed was
    O(projects) per poll — forever, in the background. It takes no session now,
    which is what keeps that from creeping back.
    """
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

    overdue, due_soon = _bucket_by_due(tasks, DUE_SOON_WINDOW_HOURS)
    for t in overdue:
        add("task_overdue", "warn", f"Task overdue: {t.title}", f"due {t.due_at}", t.id, t.due_at or now)
    for t in due_soon:
        add("task_due_soon", "info", f"Task due soon: {t.title}", f"due {t.due_at}", t.id, t.due_at or now)

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

    # #103: four batched queries for the whole feed instead of four per project.
    ids = [p.id for p in projects]
    approvals: dict[str, list[ApprovalRequest]] = {pid: [] for pid in ids}
    tasks: dict[str, list[Task]] = {pid: [] for pid in ids}
    blockers: dict[str, list[Blocker]] = {pid: [] for pid in ids}

    if ids:
        closed = status_option_service.status_keys_in_many(
            session, ids, "task", "done", "canceled"
        )
        for ap in session.exec(
            select(ApprovalRequest)
            .where(ApprovalRequest.project_id.in_(ids))  # type: ignore[attr-defined]
            .where(ApprovalRequest.status == "pending")
        ).all():
            approvals[ap.project_id].append(ap)
        for tk in session.exec(
            select(Task)
            .where(Task.project_id.in_(ids))  # type: ignore[attr-defined]
            .where(Task.due_at.is_not(None))  # type: ignore[union-attr]
            .order_by(Task.due_at)
        ).all():
            # The closed-status filter is per project (a key can be done in one
            # project and open in another), so it cannot ride along in the WHERE.
            if tk.status not in closed[tk.project_id]:
                tasks[tk.project_id].append(tk)
        for bl in session.exec(
            select(Blocker)
            .where(Blocker.project_id.in_(ids))  # type: ignore[attr-defined]
            .where(Blocker.status == "open")
        ).all():
            blockers[bl.project_id].append(bl)

    items: list[NotificationItem] = []
    for project in projects:
        items.extend(
            _project_items(
                project, approvals[project.id], tasks[project.id], blockers[project.id]
            )
        )

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
