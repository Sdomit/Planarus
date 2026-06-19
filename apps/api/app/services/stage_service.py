from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.schemas.stage import StageCreate, StageUpdate
from app.services.audit_service import create_audit_event


def list_stages(session: Session, project_id: str) -> list[Stage]:
    stmt = (
        select(Stage)
        .where(Stage.project_id == project_id)
        .order_by(Stage.sort_order, Stage.id)
    )
    return list(session.exec(stmt).all())


def get_stage(session: Session, stage_id: str) -> Optional[Stage]:
    return session.get(Stage, stage_id)


def create_stage(session: Session, project_id: str, data: StageCreate) -> Stage:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    phase = session.get(Phase, data.phase_id)
    if phase is None or phase.project_id != project_id:
        raise LookupError(f"phase '{data.phase_id}' not found in project '{project_id}'")

    sort_order = data.sort_order
    if sort_order is None:
        max_order = session.exec(
            select(func.max(Stage.sort_order)).where(Stage.phase_id == data.phase_id)
        ).first()
        sort_order = (max_order or 0) + 1

    now = now_utc()
    stage = Stage(
        id=new_id("stg"),
        phase_id=data.phase_id,
        project_id=project_id,
        title=data.title,
        description=data.description,
        status=data.status,
        sort_order=sort_order,
        created_at=now,
        updated_at=now,
    )
    session.add(stage)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="stage",
        entity_id=stage.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(stage)
    return stage


def update_stage(
    session: Session, stage_id: str, data: StageUpdate
) -> Optional[Stage]:
    stage = session.get(Stage, stage_id)
    if stage is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(stage, key, value)
    stage.updated_at = now
    session.add(stage)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="stage",
        entity_id=stage_id,
        project_id=stage.project_id,
    )
    session.commit()
    session.refresh(stage)
    return stage
