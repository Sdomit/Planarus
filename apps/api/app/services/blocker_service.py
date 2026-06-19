from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.blocker import Blocker
from app.models.project import Project
from app.models.task import Task
from app.schemas.blocker import BlockerCreate, BlockerUpdate
from app.services.audit_service import create_audit_event


def list_blockers(session: Session, project_id: str) -> list[Blocker]:
    stmt = (
        select(Blocker)
        .where(Blocker.project_id == project_id)
        .order_by(Blocker.created_at, Blocker.id)
    )
    return list(session.exec(stmt).all())


def get_blocker(session: Session, blocker_id: str) -> Optional[Blocker]:
    return session.get(Blocker, blocker_id)


def create_blocker(
    session: Session, project_id: str, data: BlockerCreate
) -> Blocker:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    if data.task_id is not None:
        task = session.get(Task, data.task_id)
        if task is None or task.project_id != project_id:
            raise LookupError(
                f"task '{data.task_id}' not found in project '{project_id}'"
            )

    now = now_utc()
    blocker = Blocker(
        id=new_id("blk"),
        project_id=project_id,
        task_id=data.task_id,
        title=data.title,
        description=data.description,
        status=data.status,
        created_at=now,
        updated_at=now,
    )
    session.add(blocker)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="blocker",
        entity_id=blocker.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(blocker)
    return blocker


def update_blocker(
    session: Session, blocker_id: str, data: BlockerUpdate
) -> Optional[Blocker]:
    blocker = session.get(Blocker, blocker_id)
    if blocker is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "task_id" in update_data and update_data["task_id"] is not None:
        task = session.get(Task, update_data["task_id"])
        if task is None or task.project_id != blocker.project_id:
            raise LookupError(
                f"task '{update_data['task_id']}' not found in project '{blocker.project_id}'"
            )

    now = now_utc()
    for key, value in update_data.items():
        setattr(blocker, key, value)
    blocker.updated_at = now
    session.add(blocker)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="blocker",
        entity_id=blocker_id,
        project_id=blocker.project_id,
    )
    session.commit()
    session.refresh(blocker)
    return blocker
