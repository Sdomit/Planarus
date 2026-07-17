from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.decision import Decision
from app.models.project import Project
from app.schemas.decision import DecisionCreate, DecisionUpdate
from app.services.audit_service import create_audit_event


def list_decisions(session: Session, project_id: str) -> list[Decision]:
    stmt = (
        select(Decision)
        .where(Decision.project_id == project_id)
        .order_by(Decision.created_at.desc(), Decision.id)
    )
    return list(session.exec(stmt).all())


def get_decision(session: Session, decision_id: str) -> Optional[Decision]:
    return session.get(Decision, decision_id)


def create_decision(
    session: Session, project_id: str, data: DecisionCreate
) -> Decision:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    now = now_utc()
    decision = Decision(
        id=new_id("dec"),
        project_id=project_id,
        title=data.title,
        context=data.context,
        decision=data.decision,
        status=data.status,
        created_at=now,
        updated_at=now,
    )
    session.add(decision)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="decision",
        entity_id=decision.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(decision)
    return decision


def update_decision(
    session: Session, decision_id: str, data: DecisionUpdate
) -> Optional[Decision]:
    decision = session.get(Decision, decision_id)
    if decision is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(decision, key, value)
    decision.updated_at = now
    session.add(decision)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="decision",
        entity_id=decision_id,
        project_id=decision.project_id,
    )
    session.commit()
    session.refresh(decision)
    return decision


def delete_decision(session: Session, decision_id: str) -> bool:
    decision = session.get(Decision, decision_id)
    if decision is None:
        return False
    project_id = decision.project_id
    session.delete(decision)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="decision",
        entity_id=decision_id,
        project_id=project_id,
    )
    session.commit()
    return True
