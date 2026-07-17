from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.todo import TodoCreate, TodoRead, TodoUpdate
from app.services import todo_service

router = APIRouter()


@router.get("/projects/{project_id}/todos", response_model=list[TodoRead])
def list_todos(
    project_id: str,
    session: Session = Depends(get_session),
) -> list[TodoRead]:
    return todo_service.list_todos(session, project_id)


@router.post(
    "/projects/{project_id}/todos",
    response_model=TodoRead,
    status_code=status.HTTP_201_CREATED,
)
def create_todo(
    project_id: str,
    data: TodoCreate,
    session: Session = Depends(get_session),
) -> TodoRead:
    try:
        return todo_service.create_todo(session, project_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.patch("/todos/{todo_id}", response_model=TodoRead)
def update_todo(
    todo_id: str,
    data: TodoUpdate,
    session: Session = Depends(get_session),
) -> TodoRead:
    try:
        todo = todo_service.update_todo(session, todo_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
    return todo


@router.delete("/todos/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not todo_service.delete_todo(session, todo_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found")
