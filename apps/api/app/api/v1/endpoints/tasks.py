from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.reorder import ReorderRequest
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services import task_service

router = APIRouter()


@router.get("/projects/{project_id}/tasks", response_model=list[TaskRead])
def list_tasks(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    return task_service.list_tasks(session, project_id)


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
        return task_service.create_task(session, project_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
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
    return task


@router.post("/projects/{project_id}/tasks/reorder", response_model=list[TaskRead])
def reorder_tasks(
    project_id: str,
    data: ReorderRequest,
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    try:
        return task_service.reorder_tasks(session, project_id, data.ids)
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
