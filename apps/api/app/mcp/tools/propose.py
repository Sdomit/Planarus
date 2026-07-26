"""Proposal-only MCP tools (Phase 7B).

Each maps 1:1 to a Phase 7A action type and calls ONLY
``approval_service.create_proposal()`` — never approve/apply/reject/invalidate and
never ``policy.handlers``. A successful call creates a single *pending*
ApprovalRequest; nothing canonical is mutated until a local human approves and
applies it. Project ownership is bound server-side; idempotency keys are derived
server-side (never accepted from the client).
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from app.core.exceptions import PolicyError, SecretDetectedError
from app.mcp.capabilities import Capability
from app.mcp.errors import (
    CODE_FORBIDDEN,
    CODE_INVALID,
    CODE_NOT_FOUND,
    CODE_SECRET,
    MCPToolError,
)
from app.mcp.serializers import ToolResult
from app.mcp.tools import StrictArgs
from app.models.doc import Doc
from app.models.task import Task
from app.prompt import boundary
from app.services import approval_service

# Kept byte-identical to the copy in app/api/external/openapi.py, which the GPT
# contract embeds; test_openapi_contract asserts the two are equal. The second
# sentence exists because the poll tool was named only in that contract (#91), so
# an MCP agent had to guess that get_approval_status was the other half of this
# loop. Both sentences ship to GPT Actions, whose descriptions cap at 300 chars —
# this string plus its 58-char schema prefix sits at 286.
REVIEW_HINT = (
    "Pending human review in Planarus Approval Queue. Nothing has changed "
    "until a local human approves and applies this exact proposal. "
    "Poll get_approval_status with this approval_id to learn the outcome "
    "and the affected entity's id."
)


# --- input schemas -----------------------------------------------------------


class CreateTaskProposalArgs(StrictArgs):
    project_id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    phase_id: Optional[str] = None
    stage_id: Optional[str] = None
    due_at: Optional[str] = None


class UpdateTaskProposalArgs(StrictArgs):
    # NOTE: no project_id — ownership is derived from task_id server-side.
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    phase_id: Optional[str] = None
    stage_id: Optional[str] = None
    due_at: Optional[str] = None


class CreateDecisionProposalArgs(StrictArgs):
    project_id: str
    title: str
    decision: str
    context: Optional[str] = None
    status: Optional[str] = None


class UpdateCanvasProposalArgs(StrictArgs):
    # NOTE: no project_id — ownership is derived from doc_id server-side.
    doc_id: str
    content_json: str  # the full new Excalidraw scene (JSON)
    markdown_cache: Optional[str] = None


class CreateConnectionProposalArgs(StrictArgs):
    project_id: str
    relation_type: str
    source_entity_type: str
    source_entity_id: str
    target_entity_type: str
    target_entity_id: str


# --- helpers -----------------------------------------------------------------


def _patch_from(args: StrictArgs, fields: tuple[str, ...]) -> dict:
    return {f: getattr(args, f) for f in fields if getattr(args, f) is not None}


def _require_propose(cap: Capability) -> None:
    # Capability-based check (shared by MCP propose tier and external API clients).
    # For an MCP propose-tier capability can_propose is True; for read it is False.
    if not cap.valid or not cap.can_propose:
        raise MCPToolError(CODE_FORBIDDEN, "propose capability required")


def _proposal_result(ar) -> ToolResult:
    metadata = {
        "approval_id": ar.id,
        "status": ar.status,
        "action_type": ar.action_type,
        "expires_at": ar.expires_at,
        "review_hint": REVIEW_HINT,
    }
    text = (
        f"{boundary.PRECEDENCE_SENTENCE}\n\n"
        f"Proposal {ar.id} created (action {ar.action_type}, status '{ar.status}').\n"
        f"{REVIEW_HINT}\n"
    )
    return ToolResult(metadata=metadata, text=text)


def _create(
    session: Session,
    cap: Capability,
    action_type: str,
    project_id: str,
    target_entity_id: Optional[str],
    patch: dict,
) -> ToolResult:
    try:
        ar = approval_service.create_proposal(
            session,
            project_id=project_id,
            action_type=action_type,
            patch=patch,
            target_entity_id=target_entity_id,
            actor_ref=cap.actor_ref,
            origin=cap.origin,
            derive_idempotency=True,
        )
    except SecretDetectedError:
        # Generic — never echo the offending value.
        raise MCPToolError(CODE_SECRET, "proposal rejected: a value looks like a secret")
    except PolicyError as exc:
        # Policy detail names fields/enums only (no values) — safe to surface.
        raise MCPToolError(CODE_INVALID, str(exc.detail))
    except LookupError:
        raise MCPToolError(CODE_NOT_FOUND, "target not found")
    return _proposal_result(ar)


# --- handlers ----------------------------------------------------------------

_TASK_FIELDS = ("title", "description", "status", "priority", "phase_id", "stage_id", "due_at")
_DECISION_FIELDS = ("title", "decision", "context", "status")
_CANVAS_FIELDS = ("content_json", "markdown_cache")
_CONNECTION_FIELDS = (
    "relation_type",
    "source_entity_type",
    "source_entity_id",
    "target_entity_type",
    "target_entity_id",
)


def create_task_proposal(
    session: Session, cap: Capability, args: CreateTaskProposalArgs
) -> ToolResult:
    _require_propose(cap)
    if not cap.allows_project(args.project_id):
        raise MCPToolError(CODE_FORBIDDEN, "project not in scope")
    return _create(session, cap, "task.create", args.project_id, None, _patch_from(args, _TASK_FIELDS))


def update_task_proposal(
    session: Session, cap: Capability, args: UpdateTaskProposalArgs
) -> ToolResult:
    _require_propose(cap)
    task = session.get(Task, args.task_id)
    # Generic not_found for missing OR out-of-scope — never reveal existence.
    if task is None or not cap.allows_project(task.project_id):
        raise MCPToolError(CODE_NOT_FOUND, "task not found")
    return _create(
        session, cap, "task.update", task.project_id, args.task_id, _patch_from(args, _TASK_FIELDS)
    )


def create_decision_proposal(
    session: Session, cap: Capability, args: CreateDecisionProposalArgs
) -> ToolResult:
    _require_propose(cap)
    if not cap.allows_project(args.project_id):
        raise MCPToolError(CODE_FORBIDDEN, "project not in scope")
    return _create(
        session, cap, "decision.create", args.project_id, None, _patch_from(args, _DECISION_FIELDS)
    )


def update_canvas_proposal(
    session: Session, cap: Capability, args: UpdateCanvasProposalArgs
) -> ToolResult:
    _require_propose(cap)
    doc = session.get(Doc, args.doc_id)
    # Generic not_found for missing / out-of-scope / non-canvas — never reveal
    # existence. Only Excalidraw canvases accept an AI content proposal here.
    if doc is None or not cap.allows_project(doc.project_id) or doc.editor_format != "excalidraw":
        raise MCPToolError(CODE_NOT_FOUND, "canvas not found")
    return _create(
        session, cap, "doc.update", doc.project_id, doc.id, _patch_from(args, _CANVAS_FIELDS)
    )


def create_connection_proposal(
    session: Session, cap: Capability, args: CreateConnectionProposalArgs
) -> ToolResult:
    """Queue one typed connection; it remains pending until human apply."""
    _require_propose(cap)
    if not cap.allows_project(args.project_id):
        raise MCPToolError(CODE_FORBIDDEN, "project not in scope")
    return _create(
        session,
        cap,
        "connection.create",
        args.project_id,
        None,
        _patch_from(args, _CONNECTION_FIELDS),
    )
