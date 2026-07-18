from typing import Iterable, Optional

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from app.core import actor
from app.core.utils import new_id, now_utc
from app.models.audit_event import AuditEvent
from app.models.user import User


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
    actor_id: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        id=new_id("aud"),
        workspace_id=workspace_id,
        project_id=project_id,
        actor_type=actor_type,
        # D32: attribution comes from the request-scoped actor context unless a
        # caller passes it explicitly. Auth off / non-HTTP callers → None.
        actor_id=actor_id if actor_id is not None else actor.current_actor_id(),
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=payload_json,
        created_at=now_utc(),
    )
    session.add(event)
    return event


def display_names(session: Session, user_ids: Iterable[Optional[str]]) -> dict[str, str]:
    """Batch-resolve user ids to display names for read models (D32).

    Unknown ids are simply absent from the result; callers fall back to what
    they rendered before. The literal ``"local"`` (pre-16 ``decided_by`` value)
    is never a user id, so it never even queries. Attribution display is
    decorative: a database whose auth tables don't exist (a local DB that has
    never run the identity migrations) must degrade to no names, never 500 a
    canonical read endpoint.
    """
    ids = {i for i in user_ids if i and i != "local"}
    if not ids:
        return {}
    try:
        rows = session.exec(select(User).where(User.id.in_(ids))).all()  # type: ignore[attr-defined]
    except OperationalError:  # e.g. no appuser table on this database
        session.rollback()
        return {}
    return {u.id: u.display_name for u in rows}
