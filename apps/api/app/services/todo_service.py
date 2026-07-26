"""Project-scoped sidebar todos with arbitrary self-nesting.

Not audited (see the model docstring): a personal scratchpad, not canonical
approval-gated state. The one non-trivial rule is re-parenting — it must stay
within the project and must not create a cycle (nesting a todo under its own
descendant).
"""
from typing import Optional

from sqlmodel import Session, select

from app.core.exceptions import NotFoundError
from app.core.utils import new_id, now_utc
from app.models.project import Project
from app.models.todo import Todo
from app.schemas.todo import TodoCreate, TodoUpdate


def list_todos(session: Session, project_id: str) -> list[Todo]:
    stmt = (
        select(Todo)
        .where(Todo.project_id == project_id)
        .order_by(Todo.sort_order, Todo.created_at, Todo.id)
    )
    return list(session.exec(stmt).all())


def _require_parent_in_project(session: Session, parent_id: str, project_id: str) -> None:
    parent = session.get(Todo, parent_id)
    if parent is None or parent.project_id != project_id:
        raise NotFoundError("parent todo not found in this project")


def create_todo(session: Session, project_id: str, data: TodoCreate) -> Todo:
    if session.get(Project, project_id) is None:
        raise NotFoundError(f"project '{project_id}' not found")
    if data.parent_id is not None:
        _require_parent_in_project(session, data.parent_id, project_id)

    now = now_utc()
    todo = Todo(
        id=new_id("td"),
        project_id=project_id,
        parent_id=data.parent_id,
        label=data.label,
        done=data.done,
        sort_order=len(list_todos(session, project_id)),  # append
        created_at=now,
        updated_at=now,
    )
    session.add(todo)
    session.commit()
    session.refresh(todo)
    return todo


def _would_cycle(session: Session, todo_id: str, new_parent_id: str) -> bool:
    """True if new_parent_id is todo_id itself or one of its descendants."""
    seen: set[str] = set()
    cur: Optional[str] = new_parent_id
    while cur is not None and cur not in seen:
        if cur == todo_id:
            return True
        seen.add(cur)
        node = session.get(Todo, cur)
        cur = node.parent_id if node is not None else None
    return False


def update_todo(session: Session, todo_id: str, data: TodoUpdate) -> Optional[Todo]:
    todo = session.get(Todo, todo_id)
    if todo is None:
        return None

    fields = data.model_dump(exclude_unset=True)
    if "parent_id" in fields and fields["parent_id"] is not None:
        _require_parent_in_project(session, fields["parent_id"], todo.project_id)
        if _would_cycle(session, todo_id, fields["parent_id"]):
            raise ValueError("cannot nest a todo under itself or its descendant")

    for key, value in fields.items():
        setattr(todo, key, value)
    todo.updated_at = now_utc()
    session.add(todo)
    session.commit()
    session.refresh(todo)
    return todo


def _delete_subtree(session: Session, todo_id: str) -> None:
    children = session.exec(select(Todo).where(Todo.parent_id == todo_id)).all()
    for child in children:
        _delete_subtree(session, child.id)
    todo = session.get(Todo, todo_id)
    if todo is not None:
        session.delete(todo)
        # Flush each node before its parent so the self-referential FK
        # (parent_id → todo.id) is never violated mid-transaction.
        session.flush()


def delete_todo(session: Session, todo_id: str) -> bool:
    if session.get(Todo, todo_id) is None:
        return False
    _delete_subtree(session, todo_id)  # cascade to descendants
    session.commit()
    return True
