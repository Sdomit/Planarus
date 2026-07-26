from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.exceptions import NotFoundError
from app.core.utils import new_id, now_utc
from app.models.blocker import Blocker
from app.models.checklist_item import ChecklistItem
from app.models.phase import Phase
from app.models.project import Project
from app.models.stage import Stage
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services import entity_connection_service, status_option_service
from app.services.audit_service import create_audit_event
from app.services.planning_reorder import apply_reorder


def _validate_status(session: Session, project_id: str, status: str) -> None:
    """A task status must be a built-in or one of the project's custom statuses."""
    if status not in status_option_service.allowed_status_keys(session, project_id, "task"):
        raise ValueError(f"status '{status}' is not defined for this project")


def _validate_assignee(session: Session, assignee_id: Optional[str]) -> None:
    """An assignee must be a real user (P16.3). ponytail: existence only — the
    picker offers workspace members, and the FK enforces referential integrity;
    add a membership check here if cross-workspace assignment ever needs blocking."""
    if assignee_id is not None and session.get(User, assignee_id) is None:
        raise ValueError(f"assignee '{assignee_id}' is not a known user")


def list_tasks(session: Session, project_id: str) -> list[Task]:
    stmt = (
        select(Task)
        .where(Task.project_id == project_id)
        .order_by(Task.sort_order, Task.id)
    )
    return list(session.exec(stmt).all())


def get_task(session: Session, task_id: str) -> Optional[Task]:
    return session.get(Task, task_id)


def _validate_parent_task(
    session: Session, project_id: str, parent_task_id: Optional[str], self_id: Optional[str] = None
) -> None:
    """A parent must exist in the same project, not be the task itself, and be a
    top-level task (nesting is capped at one level)."""
    if parent_task_id is None:
        return
    if parent_task_id == self_id:
        raise ValueError("a task cannot be its own parent")
    parent = session.get(Task, parent_task_id)
    if parent is None or parent.project_id != project_id:
        raise LookupError(
            f"parent task '{parent_task_id}' not found in project '{project_id}'"
        )
    if parent.parent_task_id is not None:
        raise ValueError("sub-tasks cannot be nested more than one level deep")


def create_task(session: Session, project_id: str, data: TaskCreate) -> Task:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")
    _validate_status(session, project_id, data.status)
    _validate_parent_task(session, project_id, data.parent_task_id)
    _validate_assignee(session, data.assignee_id)
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
        parent_task_id=data.parent_task_id,
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        sort_order=sort_order,
        due_at=data.due_at,
        assignee_id=data.assignee_id,
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

    if update_data.get("status") is not None:
        _validate_status(session, task.project_id, update_data["status"])

    if "parent_task_id" in update_data:
        _validate_parent_task(
            session, task.project_id, update_data["parent_task_id"], self_id=task.id
        )

    if "assignee_id" in update_data:
        _validate_assignee(session, update_data["assignee_id"])

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


def delete_task(session: Session, task_id: str) -> bool:
    """Delete a task, its checklist items, and unlink any blockers that pointed
    at it (blocker.task_id cleared; the blockers themselves survive)."""
    task = session.get(Task, task_id)
    if task is None:
        return False
    project_id = task.project_id
    now = now_utc()

    for item in session.exec(
        select(ChecklistItem).where(ChecklistItem.task_id == task_id)
    ).all():
        session.delete(item)
    for blocker in session.exec(
        select(Blocker).where(Blocker.task_id == task_id)
    ).all():
        blocker.task_id = None
        blocker.updated_at = now
        session.add(blocker)
    # Sub-tasks are promoted to top-level rather than deleted with the parent.
    for child in session.exec(
        select(Task).where(Task.parent_task_id == task_id)
    ).all():
        child.parent_task_id = None
        child.updated_at = now
        session.add(child)

    entity_connection_service.delete_for_entity(session, project_id, "task", task_id)

    # Flush child deletes/unlinks before the task's own DELETE (FKs enforced).
    session.flush()
    session.delete(task)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="task",
        entity_id=task_id,
        project_id=project_id,
    )
    session.commit()
    return True


def reorder_tasks(session: Session, project_id: str, ids: list[str]) -> list[Task]:
    if session.get(Project, project_id) is None:
        raise LookupError(f"project '{project_id}' not found")
    rows = {t.id: t for t in list_tasks(session, project_id)}
    return apply_reorder(
        session, project_id=project_id, entity_type="task", rows=rows, ids=ids
    )
