from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.phase import Phase
from app.models.project import Project
from app.schemas.phase import PhaseCreate, PhaseUpdate
from app.services.audit_service import create_audit_event


def list_phases(session: Session, project_id: str) -> list[Phase]:
    stmt = (
        select(Phase)
        .where(Phase.project_id == project_id)
        .order_by(Phase.sort_order, Phase.id)
    )
    return list(session.exec(stmt).all())


def get_phase(session: Session, phase_id: str) -> Optional[Phase]:
    return session.get(Phase, phase_id)


def create_phase(session: Session, project_id: str, data: PhaseCreate) -> Phase:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")

    sort_order = data.sort_order
    if sort_order is None:
        max_order = session.exec(
            select(func.max(Phase.sort_order)).where(Phase.project_id == project_id)
        ).first()
        sort_order = (max_order or 0) + 1

    now = now_utc()
    phase = Phase(
        id=new_id("ph"),
        project_id=project_id,
        title=data.title,
        description=data.description,
        status=data.status,
        sort_order=sort_order,
        created_at=now,
        updated_at=now,
    )
    session.add(phase)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="phase",
        entity_id=phase.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(phase)
    return phase


def update_phase(
    session: Session, phase_id: str, data: PhaseUpdate
) -> Optional[Phase]:
    phase = session.get(Phase, phase_id)
    if phase is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(phase, key, value)
    phase.updated_at = now
    session.add(phase)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="phase",
        entity_id=phase_id,
        project_id=phase.project_id,
    )
    session.commit()
    session.refresh(phase)
    return phase
