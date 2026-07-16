from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.calendar_event import CalendarEvent
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.models.task import Task
from app.schemas.phase import PhaseCreate, PhaseUpdate
from app.services.audit_service import create_audit_event
from app.services.planning_reorder import apply_reorder


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


def delete_phase(session: Session, phase_id: str) -> bool:
    """Delete a phase. Its tasks are unphased (phase_id/stage_id cleared),
    milestones and calendar events are unlinked (phase_id cleared), and the
    phase's stages are deleted (D-P15.3). Tasks/milestones/events survive."""
    phase = session.get(Phase, phase_id)
    if phase is None:
        return False
    project_id = phase.project_id
    now = now_utc()

    for task in session.exec(select(Task).where(Task.phase_id == phase_id)).all():
        task.phase_id = None
        task.stage_id = None
        task.updated_at = now
        session.add(task)
    for milestone in session.exec(
        select(Milestone).where(Milestone.phase_id == phase_id)
    ).all():
        milestone.phase_id = None
        milestone.updated_at = now
        session.add(milestone)
    for event in session.exec(
        select(CalendarEvent).where(CalendarEvent.phase_id == phase_id)
    ).all():
        event.phase_id = None
        event.updated_at = now
        session.add(event)
    for stage in session.exec(select(Stage).where(Stage.phase_id == phase_id)).all():
        session.delete(stage)

    # Flush the child unlinks + stage deletes so no row references the phase
    # when its own DELETE is issued (FK constraints are enforced).
    session.flush()
    session.delete(phase)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="phase",
        entity_id=phase_id,
        project_id=project_id,
    )
    session.commit()
    return True


def reorder_phases(session: Session, project_id: str, ids: list[str]) -> list[Phase]:
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    rows = {p.id: p for p in list_phases(session, project_id)}
    apply_reorder(session, project_id=project_id, entity_type="phase", rows=rows, ids=ids)
    return list_phases(session, project_id)
