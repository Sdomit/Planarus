from typing import Optional

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.checklist_item import ChecklistItem
from app.models.task import Task
from app.schemas.checklist_item import ChecklistItemCreate, ChecklistItemUpdate
from app.services.audit_service import create_audit_event


def list_checklist_items(session: Session, task_id: str) -> list[ChecklistItem]:
    stmt = (
        select(ChecklistItem)
        .where(ChecklistItem.task_id == task_id)
        .order_by(ChecklistItem.sort_order, ChecklistItem.id)
    )
    return list(session.exec(stmt).all())


def create_checklist_item(
    session: Session, task_id: str, data: ChecklistItemCreate
) -> ChecklistItem:
    task = session.get(Task, task_id)
    if task is None:
        raise ValueError(f"task '{task_id}' not found")

    # Append to the end: one past the current max sort_order. Using max()+1
    # (rather than the item count) keeps ordering stable when items are deleted.
    max_sort = session.exec(
        select(func.max(ChecklistItem.sort_order)).where(
            ChecklistItem.task_id == task_id
        )
    ).one()
    next_sort = 0 if max_sort is None else max_sort + 1
    now = now_utc()
    item = ChecklistItem(
        id=new_id("cli"),
        task_id=task_id,
        label=data.label,
        done=data.done,
        sort_order=next_sort,
        created_at=now,
        updated_at=now,
    )
    session.add(item)
    session.flush()
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="checklist_item",
        entity_id=item.id,
        project_id=task.project_id,
    )
    session.commit()
    session.refresh(item)
    return item


def delete_checklist_item(session: Session, item_id: str) -> bool:
    """Remove a checklist item. Returns True if an item was deleted, False if
    no item with that id exists."""
    item = session.get(ChecklistItem, item_id)
    if item is None:
        return False

    task = session.get(Task, item.task_id)
    session.delete(item)
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="checklist_item",
        entity_id=item_id,
        project_id=task.project_id if task is not None else None,
    )
    session.commit()
    return True


def update_checklist_item(
    session: Session, item_id: str, data: ChecklistItemUpdate
) -> Optional[ChecklistItem]:
    item = session.get(ChecklistItem, item_id)
    if item is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    item.updated_at = now_utc()
    session.add(item)

    task = session.get(Task, item.task_id)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="checklist_item",
        entity_id=item_id,
        project_id=task.project_id if task is not None else None,
    )
    session.commit()
    session.refresh(item)
    return item
