"""Bounded, project-scoped read tools (Phase 7B). Read-only: no AuditEvent, no
state change. All untrusted text is redacted + boundary-wrapped via serializers.
"""
from __future__ import annotations

from typing import Optional

from pydantic import Field
from sqlalchemy import func
from sqlmodel import Session, select

from app.mcp.capabilities import Capability
from app.mcp.errors import CODE_FORBIDDEN, CODE_NOT_FOUND, MCPToolError
from app.mcp.serializers import (
    MAX_DOC_EXCERPT_CHARS,
    MAX_FIELD_CHARS,
    MAX_LIST_ROWS,
    Block,
    ToolResult,
    build_result,
    status_only_result,
    wrap_block,
)
from app.mcp.tools import StrictArgs
from app.models.approval_request import ApprovalRequest
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.task import Task


# --- input schemas -----------------------------------------------------------


class ListProjectsArgs(StrictArgs):
    pass


class ProjectArgs(StrictArgs):
    project_id: str


class ListTasksArgs(StrictArgs):
    project_id: str
    status: Optional[str] = None
    phase_id: Optional[str] = None
    limit: int = Field(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS)


class ListScopedArgs(StrictArgs):
    project_id: str
    limit: int = Field(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS)


class ListPhaseScopedArgs(ListScopedArgs):
    """Phase 19 (D46): a project-scoped list that can narrow to one phase.
    Separate from ListScopedArgs because list_docs shares that class and Doc has
    no phase link — widening it would advertise a filter that does nothing."""

    phase_id: Optional[str] = None


class DocExcerptArgs(StrictArgs):
    doc_id: str
    max_chars: int = Field(default=MAX_DOC_EXCERPT_CHARS, ge=1, le=MAX_DOC_EXCERPT_CHARS)


class ApprovalStatusArgs(StrictArgs):
    approval_id: str


# --- helpers -----------------------------------------------------------------


def _require_project_scope(cap: Capability, project_id: str) -> None:
    if not cap.allows_project(project_id):
        raise MCPToolError(CODE_FORBIDDEN, "project not in scope")


def _fetch_capped(session: Session, stmt, limit: int):
    """Fetch up to ``limit`` rows; return (rows, truncated) via a limit+1 probe."""
    rows = list(session.exec(stmt.limit(limit + 1)).all())
    truncated = len(rows) > limit
    return rows[:limit], truncated


# --- handlers ----------------------------------------------------------------


def list_projects(session: Session, cap: Capability, args: ListProjectsArgs) -> ToolResult:
    if not cap.valid or not cap.project_ids:
        raise MCPToolError(CODE_FORBIDDEN, "no project scope")
    projects = list(
        session.exec(
            select(Project)
            .where(Project.id.in_(list(cap.project_ids)))
            .order_by(Project.id)
        ).all()
    )
    metadata = {
        "count": len(projects),
        "project_ids": [p.id for p in projects],
        "statuses": {p.id: p.status for p in projects},
    }
    blocks = [
        wrap_block(
            f"project:{p.id}",
            "project",
            [f"id: {p.id}", f"status: {p.status}", f"type: {p.project_type or '(none)'}"],
            [("title", p.title, MAX_FIELD_CHARS), ("summary", p.summary, MAX_FIELD_CHARS)],
        )
        for p in projects
    ]
    return build_result(metadata, blocks)


def get_project_summary(session: Session, cap: Capability, args: ProjectArgs) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    project = session.get(Project, args.project_id)
    if project is None:
        raise MCPToolError(CODE_NOT_FOUND, "project not found")

    def _count(model) -> int:
        return int(
            session.exec(
                select(func.count())
                .select_from(model)
                .where(model.project_id == args.project_id)
            ).one()
        )

    open_risks = int(
        session.exec(
            select(func.count())
            .select_from(Risk)
            .where(
                Risk.project_id == args.project_id,
                Risk.status.in_(["open", "monitoring"]),
            )
        ).one()
    )
    metadata = {
        "project_id": project.id,
        "status": project.status,
        "task_count": _count(Task),
        "open_risk_count": open_risks,
        "decision_count": _count(Decision),
        "doc_count": _count(Doc),
        "phase_count": _count(Phase),
    }
    block = wrap_block(
        f"project:{project.id}",
        "project",
        [f"id: {project.id}", f"status: {project.status}"],
        [("title", project.title, MAX_FIELD_CHARS), ("summary", project.summary, MAX_FIELD_CHARS)],
    )
    return build_result(metadata, [block])


def get_active_work(session: Session, cap: Capability, args: ProjectArgs) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    if session.get(Project, args.project_id) is None:
        raise MCPToolError(CODE_NOT_FOUND, "project not found")

    phases = list(
        session.exec(
            select(Phase)
            .where(Phase.project_id == args.project_id)
            .order_by(Phase.sort_order, Phase.id)
        ).all()
    )
    active_phase = next((p for p in phases if p.status == "active"), None) or next(
        (p for p in phases if p.status not in ("done", "canceled")), None
    )
    active_tasks, tasks_truncated = _fetch_capped(
        session,
        select(Task)
        .where(
            Task.project_id == args.project_id,
            Task.status.in_(["in_progress", "ready", "needs_review", "waiting"]),
        )
        .order_by(Task.sort_order, Task.id),
        MAX_LIST_ROWS,
    )
    # Phase 19 (D46): the active phase is only a complete unit if an agent also
    # sees what was decided for it and what threatens it — not just its tasks.
    phase_decisions: list[Decision] = []
    phase_risks: list[Risk] = []
    if active_phase is not None:
        phase_decisions, _ = _fetch_capped(
            session,
            select(Decision)
            .where(Decision.phase_id == active_phase.id)
            .order_by(Decision.created_at.desc(), Decision.id),
            MAX_LIST_ROWS,
        )
        phase_risks, _ = _fetch_capped(
            session,
            select(Risk)
            .where(
                Risk.phase_id == active_phase.id,
                Risk.status.in_(["open", "monitoring"]),
            )
            .order_by(Risk.created_at.desc(), Risk.id),
            MAX_LIST_ROWS,
        )

    metadata = {
        "project_id": args.project_id,
        "active_phase_id": active_phase.id if active_phase else None,
        "phase_count": len(phases),
        "active_task_count": len(active_tasks),
        "active_task_truncated": tasks_truncated,
        "phase_decision_count": len(phase_decisions),
        "phase_open_risk_count": len(phase_risks),
    }
    blocks: list[Block] = []
    if active_phase is not None:
        blocks.append(
            wrap_block(
                f"phase:{active_phase.id}",
                "phase",
                [f"id: {active_phase.id}", f"status: {active_phase.status}"],
                [("title", active_phase.title, MAX_FIELD_CHARS)],
            )
        )
    for t in active_tasks:
        blocks.append(
            wrap_block(
                f"task:{t.id}",
                "task",
                [f"id: {t.id}", f"status: {t.status}", f"priority: {t.priority or '(none)'}"],
                [("title", t.title, MAX_FIELD_CHARS)],
            )
        )
    for d in phase_decisions:
        blocks.append(
            wrap_block(
                f"decision:{d.id}",
                "decision",
                [f"id: {d.id}", f"status: {d.status}"],
                [("title", d.title, MAX_FIELD_CHARS), ("decision", d.decision, MAX_FIELD_CHARS)],
            )
        )
    for r in phase_risks:
        blocks.append(
            wrap_block(
                f"risk:{r.id}",
                "risk",
                [f"id: {r.id}", f"severity: {r.severity}", f"status: {r.status}"],
                [("title", r.title, MAX_FIELD_CHARS)],
            )
        )
    return build_result(metadata, blocks)


def list_tasks(session: Session, cap: Capability, args: ListTasksArgs) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    stmt = select(Task).where(Task.project_id == args.project_id)
    if args.status is not None:
        stmt = stmt.where(Task.status == args.status)
    if args.phase_id is not None:
        stmt = stmt.where(Task.phase_id == args.phase_id)
    stmt = stmt.order_by(Task.sort_order, Task.id)
    rows, truncated = _fetch_capped(session, stmt, args.limit)
    metadata = {
        "project_id": args.project_id,
        "count": len(rows),
        "limit": args.limit,
        "row_truncated": truncated,
        "statuses": [t.status for t in rows],
    }
    blocks = [
        wrap_block(
            f"task:{t.id}",
            "task",
            [
                f"id: {t.id}",
                f"status: {t.status}",
                f"priority: {t.priority or '(none)'}",
                f"phase_id: {t.phase_id or '(none)'}",
                f"due_at: {t.due_at or '(none)'}",
            ],
            [("title", t.title, MAX_FIELD_CHARS), ("description", t.description, MAX_FIELD_CHARS)],
        )
        for t in rows
    ]
    return build_result(metadata, blocks)


def list_decisions(
    session: Session, cap: Capability, args: ListPhaseScopedArgs
) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    stmt = select(Decision).where(Decision.project_id == args.project_id)
    if args.phase_id is not None:
        stmt = stmt.where(Decision.phase_id == args.phase_id)
    stmt = stmt.order_by(Decision.created_at.desc(), Decision.id)
    rows, truncated = _fetch_capped(session, stmt, args.limit)
    metadata = {
        "project_id": args.project_id,
        "phase_id": args.phase_id,
        "count": len(rows),
        "limit": args.limit,
        "row_truncated": truncated,
        "statuses": [d.status for d in rows],
    }
    blocks = [
        wrap_block(
            f"decision:{d.id}",
            "decision",
            [f"id: {d.id}", f"status: {d.status}", f"phase_id: {d.phase_id or '(none)'}"],
            [
                ("title", d.title, MAX_FIELD_CHARS),
                ("decision", d.decision, MAX_FIELD_CHARS),
                ("context", d.context, MAX_FIELD_CHARS),
            ],
        )
        for d in rows
    ]
    return build_result(metadata, blocks)


def list_risks(
    session: Session, cap: Capability, args: ListPhaseScopedArgs
) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    stmt = select(Risk).where(Risk.project_id == args.project_id)
    if args.phase_id is not None:
        stmt = stmt.where(Risk.phase_id == args.phase_id)
    stmt = stmt.order_by(Risk.created_at.desc(), Risk.id)
    rows, truncated = _fetch_capped(session, stmt, args.limit)
    metadata = {
        "project_id": args.project_id,
        "phase_id": args.phase_id,
        "count": len(rows),
        "limit": args.limit,
        "row_truncated": truncated,
        "severities": [r.severity for r in rows],
        "statuses": [r.status for r in rows],
    }
    blocks = [
        wrap_block(
            f"risk:{r.id}",
            "risk",
            [
                f"id: {r.id}",
                f"severity: {r.severity}",
                f"status: {r.status}",
                f"phase_id: {r.phase_id or '(none)'}",
            ],
            [("title", r.title, MAX_FIELD_CHARS), ("description", r.description, MAX_FIELD_CHARS)],
        )
        for r in rows
    ]
    return build_result(metadata, blocks)


def list_docs(session: Session, cap: Capability, args: ListScopedArgs) -> ToolResult:
    _require_project_scope(cap, args.project_id)
    stmt = (
        select(Doc)
        .where(Doc.project_id == args.project_id, Doc.archived_at.is_(None))
        .order_by(Doc.sort_order, Doc.created_at)
    )
    rows, truncated = _fetch_capped(session, stmt, args.limit)
    metadata = {
        "project_id": args.project_id,
        "count": len(rows),
        "limit": args.limit,
        "row_truncated": truncated,
        "doc_ids": [d.id for d in rows],
        "doc_types": [d.doc_type for d in rows],
    }
    # Titles only — never document bodies (use get_doc_excerpt for a bounded body).
    blocks = [
        wrap_block(
            f"doc:{d.id}",
            "doc",
            [f"id: {d.id}", f"doc_type: {d.doc_type}", f"status: {d.status}", f"version: {d.version}"],
            [("title", d.title, MAX_FIELD_CHARS)],
        )
        for d in rows
    ]
    return build_result(metadata, blocks)


def get_doc_excerpt(session: Session, cap: Capability, args: DocExcerptArgs) -> ToolResult:
    doc = session.get(Doc, args.doc_id)
    # Generic not_found for missing OR out-of-scope — never reveal existence.
    if doc is None or not cap.allows_project(doc.project_id):
        raise MCPToolError(CODE_NOT_FOUND, "document not found")
    metadata = {
        "doc_id": doc.id,
        "project_id": doc.project_id,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "version": doc.version,
        "max_chars": args.max_chars,
        "full_length": len(doc.markdown_cache or ""),
    }
    block = wrap_block(
        f"doc:{doc.id}",
        "doc",
        [f"id: {doc.id}", f"doc_type: {doc.doc_type}", f"version: {doc.version}"],
        [("title", doc.title, MAX_FIELD_CHARS), ("excerpt", doc.markdown_cache, args.max_chars)],
    )
    return build_result(metadata, [block])


def get_approval_status(
    session: Session, cap: Capability, args: ApprovalStatusArgs
) -> ToolResult:
    ar = session.get(ApprovalRequest, args.approval_id)
    if ar is None or not cap.allows_project(ar.project_id):
        raise MCPToolError(CODE_NOT_FOUND, "approval not found")
    metadata = {
        "approval_id": ar.id,
        "status": ar.status,
        "action_type": ar.action_type,
        "target_entity_type": ar.target_entity_type,
        "origin": ar.origin,
        "expires_at": ar.expires_at,
        "applied_at": ar.applied_at,
    }
    return status_only_result(metadata, note=f"Approval {ar.id} status: {ar.status}.")
