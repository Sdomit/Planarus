"""Transaction-safe apply handlers (flush only — never commit, never audit).

These deliberately do NOT call the committing CRUD services. The approval apply
transaction owns the single commit so the canonical mutation + ApprovalRequest
final state + AuditEvent are atomic. Dependency/enum validation has already run in
``approval_service`` (at proposal time and again during apply revalidation); these
handlers only perform the mutation.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.task import Task
from app.services import status_option_service


def _check_task_status(session: Session, project_id: str, status: str) -> None:
    """Phase 15.5: an applied task status must be a built-in or one of the
    project's custom statuses (the policy layer couldn't check this — it has no
    project scope)."""
    if status not in status_option_service.allowed_status_keys(session, project_id, "task"):
        raise ValueError(f"status '{status}' is not defined for this project")

_TASK_FIELDS = (
    "title",
    "description",
    "status",
    "priority",
    "phase_id",
    "stage_id",
    "due_at",
)

_DOC_FIELDS = ("content_json", "markdown_cache")


def _next_sort_order(session: Session, project_id: str) -> int:
    max_order = session.exec(
        select(func.max(Task.sort_order)).where(Task.project_id == project_id)
    ).first()
    return (max_order or 0) + 1


def _apply_task_create(session: Session, project_id: str, patch: dict) -> tuple[str, str]:
    _check_task_status(session, project_id, patch.get("status", "backlog"))
    now = now_utc()
    task = Task(
        id=new_id("tsk"),
        project_id=project_id,
        title=patch["title"],
        description=patch.get("description"),
        status=patch.get("status", "backlog"),
        priority=patch.get("priority"),
        phase_id=patch.get("phase_id"),
        stage_id=patch.get("stage_id"),
        due_at=patch.get("due_at"),
        sort_order=_next_sort_order(session, project_id),
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    return "task", task.id


def _apply_task_update(session: Session, target_id: str, patch: dict) -> tuple[str, str]:
    task = session.get(Task, target_id)
    if task is None:
        raise LookupError(f"task '{target_id}' not found")
    if patch.get("status") is not None:
        _check_task_status(session, task.project_id, patch["status"])
    for field in _TASK_FIELDS:
        if field in patch:
            setattr(task, field, patch[field])
    task.updated_at = now_utc()
    session.add(task)
    session.flush()
    return "task", task.id


def _apply_decision_create(session: Session, project_id: str, patch: dict) -> tuple[str, str]:
    now = now_utc()
    decision = Decision(
        id=new_id("dec"),
        project_id=project_id,
        title=patch["title"],
        context=patch.get("context"),
        decision=patch["decision"],
        status=patch.get("status", "proposed"),
        created_at=now,
        updated_at=now,
    )
    session.add(decision)
    session.flush()
    return "decision", decision.id


def _apply_doc_update(session: Session, target_id: str, patch: dict) -> tuple[str, str]:
    doc = session.get(Doc, target_id)
    if doc is None:
        raise LookupError(f"doc '{target_id}' not found")
    for field in _DOC_FIELDS:
        if field in patch:
            setattr(doc, field, patch[field])
    # Bump version so an open canvas editor's optimistic-concurrency guard fires
    # (it will 409 on its next autosave and reload the approved scene).
    doc.version = doc.version + 1
    doc.updated_at = now_utc()
    session.add(doc)
    session.flush()
    return "doc", doc.id


def apply_action(
    session: Session,
    *,
    action_type: str,
    project_id: str,
    target_entity_id: str | None,
    patch: dict,
) -> tuple[str, str]:
    """Perform the canonical mutation. Returns ``(entity_type, entity_id)``."""
    if action_type == "task.create":
        return _apply_task_create(session, project_id, patch)
    if action_type == "task.update":
        if target_entity_id is None:
            raise LookupError("task.update requires a target entity id")
        return _apply_task_update(session, target_entity_id, patch)
    if action_type == "decision.create":
        return _apply_decision_create(session, project_id, patch)
    if action_type == "doc.update":
        if target_entity_id is None:
            raise LookupError("doc.update requires a target entity id")
        return _apply_doc_update(session, target_entity_id, patch)
    raise LookupError(f"no apply handler for action {action_type!r}")
