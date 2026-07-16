from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.checklist_item import (
    ChecklistItemCreate,
    ChecklistItemRead,
    ChecklistItemUpdate,
)
from app.services import checklist_service

router = APIRouter()


@router.get(
    "/tasks/{task_id}/checklist-items", response_model=list[ChecklistItemRead]
)
def list_checklist_items(
    task_id: str,
    session: Session = Depends(get_session),
) -> list[ChecklistItemRead]:
    return checklist_service.list_checklist_items(session, task_id)


@router.post(
    "/tasks/{task_id}/checklist-items",
    response_model=ChecklistItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_checklist_item(
    task_id: str,
    data: ChecklistItemCreate,
    session: Session = Depends(get_session),
) -> ChecklistItemRead:
    try:
        return checklist_service.create_checklist_item(session, task_id, data)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")


@router.patch("/checklist-items/{item_id}", response_model=ChecklistItemRead)
def update_checklist_item(
    item_id: str,
    data: ChecklistItemUpdate,
    session: Session = Depends(get_session),
) -> ChecklistItemRead:
    item = checklist_service.update_checklist_item(session, item_id, data)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found"
        )
    return item


@router.delete(
    "/checklist-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_checklist_item(
    item_id: str,
    session: Session = Depends(get_session),
) -> None:
    if not checklist_service.delete_checklist_item(session, item_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Checklist item not found"
        )
