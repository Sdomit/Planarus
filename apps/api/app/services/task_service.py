from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.audit_service import create_audit_event


def list_tasks(session: Session, project_id: str) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order, Task.id)
    )
    return list(session.exec(stmt).all())


def get_task(session: Session, task_id: str) -> Optional[Task]:
    return session.get(Task, task_id)


def create_task(session: Session, project_id: str, data: TaskCreate) -> Task:
    if session.get(Project, project_id) is None:
        raise ValueError(f"project '{project_id}' not found")
    if data.phase_id is not None:
        phase = session.get(Phase, data.phase_id)
        if phase is None or phase.project_id != project_id:
            raise LookupError(
                f"phase '{data.phase_id}' not found in project '{project_id}'"
            )
    if data.stage_id is not None:
        stage = session.get(Stage, data.stage_id)
        if stage is None or stage.project_id != project_id:
            raise LookupError(
                f"stage '{data.stage_id}' not found in project '{project_id}'"
            )

    sort_order = data.sort_order
    if sort_order is None:
        max_order = session.exec(
            select(func.max(Task.sort_order)).where(Task.project_id == project_id)
        ).first()
        sort_order = (max_order or 0) + 1

    now = now_utc()
    task = Task(
        id=new_id("tsk"),
        project_id=project_id,
        phase_id=data.phase_id,
        stage_id=data.stage_id,
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        sort_order=sort_order,
        due_at=data.due_at,
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="task",
        entity_id=task.id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(task)
    return task


def update_task(session: Session, task_id: str, data: TaskUpdate) -> Optional[Task]:
    task = session.get(Task, task_id)
    if task is None:
        return None

    update_data = data.model_dump(exclude_unset=True)

    if "phase_id" in update_data and update_data["phase_id"] is not None:
        phase = session.get(Phase, update_data["phase_id"])
        if phase is None or phase.project_id != task.project_id:
            raise LookupError(
                f"phase '{update_data['phase_id']}' not found in project '{task.project_id}'"
            )

    if "stage_id" in update_data and update_data["stage_id"] is not None:
        stage = session.get(Stage, update_data["stage_id"])
        if stage is None or stage.project_id != task.project_id:
            raise LookupError(
                f"stage '{update_data['stage_id']}' not found in project '{task.project_id}'"
            )

    # After the patch, both effective values being non-null requires the stage to belong to the phase.
    effective_phase_id = update_data.get("phase_id", task.phase_id)
    effective_stage_id = update_data.get("stage_id", task.stage_id)
    if effective_phase_id is not None and effective_stage_id is not None:
        stage = session.get(Stage, effective_stage_id)
        if stage is None or stage.phase_id != effective_phase_id:
            raise ValueError(
                f"stage '{effective_stage_id}' does not belong to phase '{effective_phase_id}'"
            )

    now = now_utc()
    for key, value in update_data.items():
        setattr(task, key, value)
    task.updated_at = now
    session.add(task)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="task",
        entity_id=task_id,
        project_id=task.project_id,
    )
    session.commit()
    session.refresh(task)
    return task
