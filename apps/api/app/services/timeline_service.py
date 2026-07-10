from sqlmodel import Session, select

from app.core.utils import now_utc
from app.models.agent_run import AgentRun
from app.models.approval_request import ApprovalRequest
from app.models.audit_event import AuditEvent
from app.models.blocker import Blocker
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.email_log import EmailLog
from app.models.notification_rule import NotificationRule
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task
from app.schemas.timeline import ProjectTimeline, TimelineEvent

# entity_type (as written by services into AuditEvent) → (model, label attribute)
_RESOLVERS = {
    "task": (Task, "title"),
    "phase": (Phase, "title"),
    "stage": (Stage, "title"),
    "decision": (Decision, "title"),
    "risk": (Risk, "title"),
    "blocker": (Blocker, "title"),
    "doc": (Doc, "title"),
    "project": (Project, "title"),
    "agent_run": (AgentRun, "agent_family"),
    "approval_request": (ApprovalRequest, "action_type"),
    "notification_rule": (NotificationRule, "to_email"),
    "email_log": (EmailLog, "subject"),
}


def build_timeline(session: Session, project_id: str, limit: int = 50) -> ProjectTimeline:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    events = list(
        session.exec(
            select(AuditEvent)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())  # type: ignore[attr-defined]
            .limit(limit)
        ).all()
    )

    # Resolve display names in one query per entity type present on this page.
    titles: dict[tuple[str, str], str] = {}
    wanted: dict[str, set[str]] = {}
    for ev in events:
        if ev.entity_id and ev.entity_type in _RESOLVERS:
            wanted.setdefault(ev.entity_type, set()).add(ev.entity_id)
    for entity_type, ids in wanted.items():
        model, attr = _RESOLVERS[entity_type]
        for row in session.exec(select(model).where(model.id.in_(ids))).all():  # type: ignore[attr-defined]
            titles[(entity_type, row.id)] = str(getattr(row, attr))

    items: list[TimelineEvent] = []
    for ev in events:
        title = titles.get((ev.entity_type, ev.entity_id)) if ev.entity_id else None
        label = f"{ev.event_type} {ev.entity_type}".replace("_", " ")
        if title:
            label = f"{label} — {title}"
        items.append(
            TimelineEvent(
                id=ev.id,
                at=ev.created_at,
                event_type=ev.event_type,
                entity_type=ev.entity_type,
                entity_id=ev.entity_id,
                actor_type=ev.actor_type,
                label=label,
            )
        )
    return ProjectTimeline(
        project_id=project_id, generated_at=now_utc(), events=items
    )
