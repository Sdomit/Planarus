from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.schemas.milestone import MilestoneCreate, MilestoneUpdate
from app.services.audit_service import create_audit_event


def list_milestones(session: Session, project_id: str) -> list[Milestone]:
    stmt = (
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.sort_order, Milestone.id)
    )
    return list(session.exec(stmt).all())


def _validate_phase(session: Session, project_id: str, phase_id: Optional[str]) -> None:
    if phase_id is None:
        return
    phase = session.get(Phase, phase_id)
    if phase is None or phase.project_id != project_id:
        raise LookupError(f"phase '{phase_id}' not found in project '{project_id}'")


def create_milestone(
    session: Session, project_id: str, data: MilestoneCreate
) -> Milestone:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    _validate_phase(session, project_id, data.phase_id)

    now = now_utc()
    milestone = Milestone(
        id=new_id("mil"),
        project_id=project_id,
        phase_id=data.phase_id,
        title=data.title,
        description=data.description,
        status=data.status,
        target_date=data.target_date,
        created_at=now,
        updated_at=now,
    )
    session.add(milestone)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="milestone",
        entity_id=milestone.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(milestone)
    return milestone


def update_milestone(
    session: Session, milestone_id: str, data: MilestoneUpdate
) -> Optional[Milestone]:
    milestone = session.get(Milestone, milestone_id)
    if milestone is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    if "phase_id" in update_data:
        _validate_phase(session, milestone.project_id, update_data["phase_id"])

    for key, value in update_data.items():
        setattr(milestone, key, value)
    milestone.updated_at = now_utc()
    session.add(milestone)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="milestone",
        entity_id=milestone_id,
        project_id=milestone.project_id,
    )
    session.commit()
    session.refresh(milestone)
    return milestone
