from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.reorder import ReorderRequest
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import audit_service, task_service

router = APIRouter()


def _read(session: Session, tasks) -> list[TaskRead]:
    """Coerce Task rows to reads with assignee_display resolved (P16.3, D33).
    One batch lookup; unassigned/local-mode rows keep display None."""
    items = [TaskRead.model_validate(t) for t in tasks]
    names = audit_service.display_names(session, (i.assignee_id for i in items))
    for i in items:
        i.assignee_display = names.get(i.assignee_id) if i.assignee_id else None
    return items


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
def list_tasks(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    return _read(session, task_service.list_tasks(session, project_id))


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    project_id: str,
    data: TaskCreate,
    session: Session = Depends(get_session),
) -> TaskRead:
    try:
        return _read(session, [task_service.create_task(session, project_id, data)])[0]
    except ValueError as exc:
        # Project-not-found → 404; a validation error (e.g. illegal nesting) → 422.
        if "project" in str(exc) and "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: str,
    data: TaskUpdate,
    session: Session = Depends(get_session),
) -> TaskRead:
    try:
        task = task_service.update_task(session, task_id, data)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return _read(session, [task])[0]


@router.post("/projects/{project_id}/tasks/reorder", response_model=list[TaskRead])
def reorder_tasks(
    project_id: str,
    data: ReorderRequest,
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    try:
        return _read(session, task_service.reorder_tasks(session, project_id, data.ids))
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not task_service.delete_task(session, task_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
