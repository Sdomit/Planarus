"""Bounded, project-scoped read tools (Phase 7B). Read-only: no AuditEvent, no
state change. All untrusted text is redacted + boundary-wrapped via serializers.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field
from sqlalchemy import func
from sqlmodel import Session, select

from app.core.constants import BUILTIN_STATUS_KEYS
from app.mcp.capabilities import Capability
from app.mcp.errors import CODE_FORBIDDEN, CODE_NOT_FOUND, MCPToolError
from app.mcp.serializers import (
    MAX_DETAIL_CHARS,
    MAX_DOC_EXCERPT_CHARS,
    MAX_FIELD_CHARS,
    MAX_LIST_ROWS,
    Block,
    ToolResult,
    build_result,
    redact,
    status_only_result,
    wrap_block,
)
from app.mcp.tools import StrictArgs
from app.models.approval_request import ApprovalRequest
from app.models.blocker import Blocker
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.task import Task
from app.services import approval_service, status_option_service

# The built-in task statuses that count as work in flight. Deliberately narrower
# than "everything open": `backlog` and `blocked` are open but are not what an
# agent is being handed. Custom statuses in the open category are added to this
# per project (#88) — before that, a project whose board said "In review" was
# invisible here no matter how much work sat in it.
_ACTIVE_BUILTIN_TASK_STATUSES = ("in_progress", "ready", "needs_review", "waiting")


# --- input schemas -----------------------------------------------------------


class ListProjectsArgs(StrictArgs):
    pass


class ProjectArgs(StrictArgs):
    project_id: str


# #92: every list tool capped at MAX_LIST_ROWS with no offset meant a project
# past that cap had rows no agent surface could ever reach — its only move was to
# guess filters. `offset` is the lever; `next_offset` in the result metadata tells
# the agent what to pass next, so paging needs no arithmetic on its side.
_OFFSET_FIELD = Field(
    default=0, ge=0, description="Rows to skip; pass `next_offset` from the previous page."
)


class ListTasksArgs(StrictArgs):
    project_id: str
    status: Optional[str] = None
    phase_id: Optional[str] = None
    limit: int = Field(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS)
    offset: int = _OFFSET_FIELD


class ListScopedArgs(StrictArgs):
    project_id: str
    limit: int = Field(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS)
    offset: int = _OFFSET_FIELD


class ListPhaseScopedArgs(ListScopedArgs):
    """Phase 19 (D46): a project-scoped list that can narrow to one phase.
    Separate from ListScopedArgs because list_docs shares that class and Doc has
    no phase link — widening it would advertise a filter that does nothing."""

    phase_id: Optional[str] = None


class DocExcerptArgs(StrictArgs):
    doc_id: str
    max_chars: int = Field(default=MAX_DOC_EXCERPT_CHARS, ge=1, le=MAX_DOC_EXCERPT_CHARS)
    # #92: without this, chars beyond max_chars were unreachable through any agent
    # surface — the tool reported full_length but offered no way to read past it.
    offset: int = Field(
        default=0, ge=0, description="Characters to skip; pass `next_offset` to continue."
    )


class ApprovalStatusArgs(StrictArgs):
    approval_id: str


class GetItemArgs(StrictArgs):
    """#92: one parameterized detail read, rather than one tool per entity type.

    Keeps the read tier's tool count near-flat while giving every listable type a
    route to its untruncated fields.
    """

    kind: Literal["task", "decision", "risk", "doc"]
    item_id: str


# --- helpers -----------------------------------------------------------------


def _require_project_scope(cap: Capability, project_id: str) -> None:
    if not cap.allows_project(project_id):
        raise MCPToolError(CODE_FORBIDDEN, "project not in scope")


def _fetch_capped(session: Session, stmt, limit: int, offset: int = 0):
    """Fetch up to ``limit`` rows from ``offset``; (rows, truncated) via limit+1."""
    if offset:
        stmt = stmt.offset(offset)
    rows = list(session.exec(stmt.limit(limit + 1)).all())
    truncated = len(rows) > limit
    return rows[:limit], truncated


def _page_metadata(limit: int, offset: int, count: int, truncated: bool) -> dict:
    """Paging scalars shared by every list tool.

    ``next_offset`` is None on the last page, so "keep going while next_offset is
    not null" is the whole client-side contract.
    """
    return {
        "limit": limit,
        "offset": offset,
        "row_truncated": truncated,
        "next_offset": offset + count if truncated else None,
    }


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
    finished_phases = status_option_service.status_keys_in(
        session, args.project_id, "phase", "done", "canceled"
    )
    active_phase = next((p for p in phases if p.status == "active"), None) or next(
        (p for p in phases if p.status not in finished_phases), None
    )
    open_tasks = status_option_service.status_keys_in(
        session, args.project_id, "task", "open"
    )
    active_task_statuses = set(_ACTIVE_BUILTIN_TASK_STATUSES) | (
        open_tasks - set(BUILTIN_STATUS_KEYS["task"])
    )
    active_tasks, tasks_truncated = _fetch_capped(
        session,
        select(Task)
        .where(
            Task.project_id == args.project_id,
            Task.status.in_(active_task_statuses),
        )
        .order_by(Task.sort_order, Task.id),
        MAX_LIST_ROWS,
    )
    # Phase 19 (D46): the active phase is only a complete unit if an agent also
    # sees what was decided for it and what threatens it — not just its tasks.
    phase_decisions: list[Decision] = []
    phase_risks: list[Risk] = []
    if active_phase is not None:
        # project_id is not redundant with phase_id: the FK only requires that
        # the phase exist, not that it belong to this project. Scope every row
        # to the capability's project like every other handler here, so a
        # cross-project link can never splice foreign text into this brief.
        phase_decisions, _ = _fetch_capped(
            session,
            select(Decision)
            .where(
                Decision.project_id == args.project_id,
                Decision.phase_id == active_phase.id,
            )
            .order_by(Decision.created_at.desc(), Decision.id),
            MAX_LIST_ROWS,
        )
        phase_risks, _ = _fetch_capped(
            session,
            select(Risk)
            .where(
                Risk.project_id == args.project_id,
                Risk.phase_id == active_phase.id,
                Risk.status.in_(["open", "monitoring"]),
            )
            .order_by(Risk.created_at.desc(), Risk.id),
            MAX_LIST_ROWS,
        )

    # #93: open blockers were invisible to every agent surface — `grep Blocker
    # app/mcp/` returned zero hits. The one entity type whose entire purpose is
    # "don't work on this yet" was the one an agent could not see. Project-scoped,
    # not phase-scoped: Blocker has no phase_id.
    open_blockers, blockers_truncated = _fetch_capped(
        session,
        select(Blocker)
        .where(Blocker.project_id == args.project_id, Blocker.status == "open")
        .order_by(Blocker.created_at.desc(), Blocker.id),
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
        "open_blocker_count": len(open_blockers),
        "open_blocker_truncated": blockers_truncated,
        # Safe scalars only — the roster's titles live in the wrapped block below.
        "phase_ids": [p.id for p in phases[:MAX_LIST_ROWS]],
    }
    blocks: list[Block] = []

    # #93: no tool listed phases, so the phase_id scalar on every task/decision/
    # risk row was an unresolvable opaque token. One compact block resolves the
    # whole roster; each title is redacted and clipped individually.
    #
    # Ids are NOT put in the block text: build_result's defence-in-depth rescan
    # masks them as high-entropy strings, so a text id reads back as
    # «redacted:high-entropy-string». Ids ride in metadata["phase_ids"] (they are
    # safe scalars) and the text lines are index-labelled in the SAME order, so
    # phase_ids[i] names the phase described by phase[i].
    if phases:
        blocks.append(
            wrap_block(
                f"project:{args.project_id}:phases",
                "phase_roster",
                [
                    f"phase_count: {len(phases)}",
                    "note: phase[i] corresponds to metadata.phase_ids[i]",
                ],
                [
                    (f"phase[{i}]", f"{p.status} · {p.title}", MAX_FIELD_CHARS)
                    for i, p in enumerate(phases[:MAX_LIST_ROWS])
                ],
            )
        )
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
    for b in open_blockers:
        blocks.append(
            wrap_block(
                f"blocker:{b.id}",
                "blocker",
                [
                    f"id: {b.id}",
                    f"status: {b.status}",
                    f"task_id: {b.task_id or '(none)'}",
                ],
                [
                    ("title", b.title, MAX_FIELD_CHARS),
                    ("description", b.description, MAX_FIELD_CHARS),
                ],
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
    rows, truncated = _fetch_capped(session, stmt, args.limit, args.offset)
    metadata = {
        "project_id": args.project_id,
        "count": len(rows),
        **_page_metadata(args.limit, args.offset, len(rows), truncated),
        # #153 review: ids live here, not in the block text. The
        # defence-in-depth rescan masks them as high-entropy strings, so a
        # text id reads back as «redacted:…» and get_item could not be
        # called for these kinds at all. Order matches the blocks below.
        "task_ids": [t.id for t in rows],
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
    rows, truncated = _fetch_capped(session, stmt, args.limit, args.offset)
    metadata = {
        "project_id": args.project_id,
        "phase_id": args.phase_id,
        "count": len(rows),
        **_page_metadata(args.limit, args.offset, len(rows), truncated),
        # #153 review: ids live here, not in the block text. The
        # defence-in-depth rescan masks them as high-entropy strings, so a
        # text id reads back as «redacted:…» and get_item could not be
        # called for these kinds at all. Order matches the blocks below.
        "decision_ids": [d.id for d in rows],
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
    rows, truncated = _fetch_capped(session, stmt, args.limit, args.offset)
    metadata = {
        "project_id": args.project_id,
        "phase_id": args.phase_id,
        "count": len(rows),
        **_page_metadata(args.limit, args.offset, len(rows), truncated),
        # #153 review: ids live here, not in the block text. The
        # defence-in-depth rescan masks them as high-entropy strings, so a
        # text id reads back as «redacted:…» and get_item could not be
        # called for these kinds at all. Order matches the blocks below.
        "risk_ids": [r.id for r in rows],
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
    rows, truncated = _fetch_capped(session, stmt, args.limit, args.offset)
    metadata = {
        "project_id": args.project_id,
        "count": len(rows),
        **_page_metadata(args.limit, args.offset, len(rows), truncated),
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


def doc_excerpt_result(
    session: Session, cap: Capability, doc_id: str, max_chars: int, offset: int
) -> ToolResult:
    """Shared by the get_doc_excerpt tool (bounded by DocExcerptArgs' Field cap)
    and the doc resource read (#184 — a much larger internal cap, since a
    resource read is meant to sidestep pagination for the common case rather
    than page through it). Same not_found/redact/wrap pipeline either way —
    a resource is not a lower-scrutiny path than a tool call.
    """
    doc = session.get(Doc, doc_id)
    # Generic not_found for missing OR out-of-scope — never reveal existence.
    if doc is None or not cap.allows_project(doc.project_id):
        raise MCPToolError(CODE_NOT_FOUND, "document not found")
    # Page over the REDACTED representation, not the raw one. wrap_block redacts
    # before it clips (deliberately — a secret straddling the cap must not survive
    # as a fragment), and a placeholder is a different length from the span it
    # replaces: «redacted:aws-access-key» is 25 chars for a 20-char key. Offsets
    # counted on raw text therefore describe a different span than the page
    # actually showed, so the next page skipped or repeated neighbouring text.
    #
    # Offsets now index what the caller can actually see, which is the only
    # coherent unit for a paging loop. Redaction is idempotent, so wrap_block
    # re-redacting this below is a no-op.
    body, _labels = redact(doc.markdown_cache or "")
    full_length = len(body)
    # Hand wrap_block the whole tail from `offset` and let it do the clipping, so
    # the in-text "…(truncated, N more chars)" marker still fires and still counts
    # the true remainder. `window` below is only for the paging scalars. An offset
    # at or past the end yields an empty excerpt rather than an error — the natural
    # "you have read it all" terminator for a paging loop.
    tail = body[offset:]
    window = tail[:max_chars]
    has_more = offset + len(window) < full_length
    metadata = {
        "doc_id": doc.id,
        "project_id": doc.project_id,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "version": doc.version,
        "max_chars": max_chars,
        "offset": offset,
        "full_length": full_length,
        "excerpt_length": len(window),
        "next_offset": offset + len(window) if has_more else None,
    }
    block = wrap_block(
        f"doc:{doc.id}",
        "doc",
        [f"id: {doc.id}", f"doc_type: {doc.doc_type}", f"version: {doc.version}"],
        [("title", doc.title, MAX_FIELD_CHARS), ("excerpt", tail, max_chars)],
    )
    return build_result(metadata, [block])


def get_doc_excerpt(session: Session, cap: Capability, args: DocExcerptArgs) -> ToolResult:
    return doc_excerpt_result(session, cap, args.doc_id, args.max_chars, args.offset)


# kind -> (model, scalar-line builder, text fields to render at MAX_DETAIL_CHARS).
# Scalars stay separate from wrapped text: raw titles/descriptions never leak into
# metadata (the module contract at the top of this file).
_DETAIL_SPECS: dict[str, tuple] = {
    "task": (
        Task,
        lambda o: [
            f"id: {o.id}",
            f"status: {o.status}",
            f"priority: {o.priority or '(none)'}",
            f"phase_id: {o.phase_id or '(none)'}",
            f"due_at: {o.due_at or '(none)'}",
        ],
        lambda o: [("title", o.title), ("description", o.description)],
    ),
    "decision": (
        Decision,
        lambda o: [
            f"id: {o.id}",
            f"status: {o.status}",
            f"phase_id: {o.phase_id or '(none)'}",
        ],
        lambda o: [
            ("title", o.title),
            ("decision", o.decision),
            ("context", o.context),
        ],
    ),
    "risk": (
        Risk,
        lambda o: [
            f"id: {o.id}",
            f"severity: {o.severity}",
            f"status: {o.status}",
            f"phase_id: {o.phase_id or '(none)'}",
        ],
        lambda o: [
            ("title", o.title),
            ("description", o.description),
            ("mitigation", o.mitigation),
        ],
    ),
    "doc": (
        Doc,
        lambda o: [
            f"id: {o.id}",
            f"doc_type: {o.doc_type}",
            f"status: {o.status}",
            f"version: {o.version}",
        ],
        # Body deliberately excluded — a doc body is unbounded and belongs to
        # get_doc_excerpt, which pages it. This returns the doc's own fields only.
        lambda o: [("title", o.title)],
    ),
}


def get_item(session: Session, cap: Capability, args: GetItemArgs) -> ToolResult:
    model, scalars, text_fields = _DETAIL_SPECS[args.kind]
    obj = session.get(model, args.item_id)
    # Generic not_found for missing OR out-of-scope — never reveal existence.
    if obj is None or not cap.allows_project(obj.project_id):
        raise MCPToolError(CODE_NOT_FOUND, f"{args.kind} not found")

    metadata = {
        "kind": args.kind,
        "item_id": obj.id,
        "project_id": obj.project_id,
        "max_chars": MAX_DETAIL_CHARS,
    }
    block = wrap_block(
        f"{args.kind}:{obj.id}",
        args.kind,
        scalars(obj),
        [(name, value, MAX_DETAIL_CHARS) for name, value in text_fields(obj)],
    )
    return build_result(metadata, [block])


def get_approval_status(
    session: Session, cap: Capability, args: ApprovalStatusArgs
) -> ToolResult:
    ar = session.get(ApprovalRequest, args.approval_id)
    if ar is None or not cap.allows_project(ar.project_id):
        raise MCPToolError(CODE_NOT_FOUND, "approval not found")
    # The three id keys close the propose -> approve -> apply loop (#91): without
    # them an agent's only way back to what it created was list_tasks plus a fuzzy
    # title match, which picks the wrong row whenever two titles are similar. All
    # three are always present, null before apply, so a poller sees one shape.
    applied_entity_type, applied_entity_id = approval_service.applied_entity(session, ar)
    metadata = {
        "approval_id": ar.id,
        "status": ar.status,
        "action_type": ar.action_type,
        "target_entity_type": ar.target_entity_type,
        "target_entity_id": ar.target_entity_id,
        "applied_entity_type": applied_entity_type,
        "applied_entity_id": applied_entity_id,
        "origin": ar.origin,
        "expires_at": ar.expires_at,
        "applied_at": ar.applied_at,
    }
    return status_only_result(metadata, note=f"Approval {ar.id} status: {ar.status}.")
