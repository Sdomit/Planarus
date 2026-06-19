from typing import Optional

from sqlmodel import Session

from app.core.utils import new_id, now_utc
from app.models.audit_event import AuditEvent


def create_audit_event(
    session: Session,
    *,
    event_type: str,
    actor_type: str,
    entity_type: str,
    entity_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
    payload_json: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        id=new_id("aud"),
        workspace_id=workspace_id,
        project_id=project_id,
        actor_type=actor_type,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
        created_at=now_utc(),
    )
    session.add(event)
    return event
