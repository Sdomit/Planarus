from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.link import Link
from app.models.project import Project
from app.schemas.link import LinkCreate
from app.services.audit_service import create_audit_event
from app.services.entity_ref import validate_entity_ref


def list_links(
    session: Session,
    project_id: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> list[Link]:
    stmt = select(Link).where(Link.project_id == project_id)
    if entity_type is not None:
        stmt = stmt.where(Link.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(Link.entity_id == entity_id)
    stmt = stmt.order_by(Link.created_at, Link.id)
    return list(session.exec(stmt).all())


def create_link(session: Session, project_id: str, data: LinkCreate) -> Link:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    validate_entity_ref(session, project_id, data.entity_type, data.entity_id)

    link = Link(
        id=new_id("lnk"),
        project_id=project_id,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        url=data.url,
        title=data.title,
        created_at=now_utc(),
    )
    session.add(link)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="link",
        entity_id=link.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(link)
    return link
