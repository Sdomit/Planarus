"""External API routes (Phase 7C1): bounded reads + pending proposals only.

Every route reuses the Phase 7B shared handlers/serializers verbatim — project
scope enforcement, boundary-wrapping, defanging, secret masking (redact-before-clip
+ assembled-output rescan), row/excerpt caps, proposal policy validation, secret
rejection, target binding, idempotency, and audit metadata all come from the shared
code. This module is a thin HTTP adapter that maps MCPToolError → RFC 9457
problem+json. There is NO approve/apply/reject/invalidate/mutation route.
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session

from app.api.external.auth import require_external_propose, require_external_read
from app.api.external.problems import ExternalProblem
from app.db.session import get_session
from app.mcp.capabilities import Capability
from app.mcp.errors import (
    CODE_FORBIDDEN,
    CODE_INTERNAL,
    CODE_INVALID,
    CODE_NOT_FOUND,
    CODE_SECRET,
    CODE_TOO_LARGE,
    CODE_UNAVAILABLE,
    MCPToolError,
)
from app.mcp.serializers import MAX_DOC_EXCERPT_CHARS, MAX_LIST_ROWS
from app.mcp.tools import StrictArgs
from app.mcp.tools import propose as propose_tools
from app.mcp.tools import read as read_tools

router = APIRouter()


class _TaskUpdateBody(StrictArgs):
    """Body for task update — task_id comes from the path (ownership server-side)."""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    phase_id: Optional[str] = None
    stage_id: Optional[str] = None
    due_at: Optional[str] = None

# Defence-in-depth: no external route name may imply a forbidden verb/surface.
_FORBIDDEN_PATH_SUBSTRINGS = (
    "approve", "apply", "reject", "invalidate", "delete", "archive", "export",
    "filesystem", "shell", "command", "git", "chatgpt", "import", "tunnel", "oauth",
)


def _map_mcp_error(exc: MCPToolError) -> ExternalProblem:
    code = exc.code
    if code in (CODE_FORBIDDEN, CODE_NOT_FOUND):
        # Hide existence/scope: out-of-scope, unknown, or cross-workspace → 404.
        return ExternalProblem(
            404, "not_found", "Not Found",
            "the requested resource was not found or is not in scope",
        )
    if code == CODE_INVALID:
        # Policy detail names fields/enums only (no values) — safe to surface.
        return ExternalProblem(422, "validation_error", "Unprocessable Entity", exc.message)
    if code == CODE_SECRET:
        return ExternalProblem(
            422, "secret_detected", "Unprocessable Entity",
            "a proposed value looks like a secret and was rejected",
        )
    if code == CODE_TOO_LARGE:
        return ExternalProblem(413, "payload_too_large", "Payload Too Large", "request exceeds the size limit")
    if code == CODE_UNAVAILABLE:
        return ExternalProblem(503, "unavailable", "Service Unavailable", "Planarus data is temporarily unavailable")
    # CODE_INTERNAL or anything unexpected — never leak detail.
    assert code == CODE_INTERNAL or True
    return ExternalProblem(500, "internal_error", "Internal Server Error", "internal error")


def _run_read(session: Session, cap: Capability, handler, args) -> dict:
    try:
        result = handler(session, cap, args)
    except MCPToolError as exc:
        raise _map_mcp_error(exc)
    except (OperationalError, ProgrammingError):
        raise ExternalProblem(
            503, "unavailable", "Service Unavailable",
            "Planarus data is temporarily unavailable",
        )
    # metadata = safe scalars only; text = precedence sentence + boundary-wrapped,
    # redacted content. Raw project text is never duplicated into metadata.
    return {"metadata": result.metadata, "text": result.text}


def _run_propose(session: Session, cap: Capability, handler, args) -> dict:
    try:
        result = handler(session, cap, args)
    except MCPToolError as exc:
        raise _map_mcp_error(exc)
    except (OperationalError, ProgrammingError):
        raise ExternalProblem(
            503, "unavailable", "Service Unavailable",
            "Planarus data is temporarily unavailable",
        )
    # Proposal result is exactly {approval_id, status, action_type, expires_at,
    # review_hint} — never the diff/patch.
    return dict(result.metadata)


async def _parse_json_body(request: Request, model: type[BaseModel]) -> BaseModel:
    ctype = request.headers.get("content-type", "")
    if ctype.split(";")[0].strip().lower() != "application/json":
        raise ExternalProblem(
            415, "unsupported_media_type", "Unsupported Media Type",
            "Content-Type must be application/json",
        )
    body = await request.body()
    try:
        data = json.loads(body) if body else None
    except (json.JSONDecodeError, ValueError):
        raise ExternalProblem(400, "malformed_json", "Bad Request", "request body is not valid JSON")
    if not isinstance(data, dict):
        raise ExternalProblem(400, "malformed_json", "Bad Request", "request body must be a JSON object")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        fields = sorted({".".join(str(p) for p in e["loc"]) for e in exc.errors()})
        raise ExternalProblem(
            422, "validation_error", "Unprocessable Entity",
            f"invalid or unknown field(s): {', '.join(fields) or 'schema mismatch'}",
        )


# --- read routes (require can_read) ------------------------------------------


@router.get("/projects")
def list_projects(
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(session, cap, read_tools.list_projects, read_tools.ListProjectsArgs())


@router.get("/projects/{project_id}/summary")
def project_summary(
    project_id: str,
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.get_project_summary,
        read_tools.ProjectArgs(project_id=project_id),
    )


@router.get("/projects/{project_id}/active-work")
def active_work(
    project_id: str,
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    """#93: the orientation call. Without it on this surface a Custom GPT needed
    four round trips (summary + tasks + decisions + risks) to learn what one call
    already returns — and still could not see blockers or resolve a phase_id."""
    return _run_read(
        session, cap, read_tools.get_active_work,
        read_tools.ProjectArgs(project_id=project_id),
    )


@router.get("/projects/{project_id}/tasks")
def list_tasks(
    project_id: str,
    status: Optional[str] = None,
    phase_id: Optional[str] = None,
    limit: int = Query(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS),
    offset: int = Query(default=0, ge=0),
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.list_tasks,
        read_tools.ListTasksArgs(
            project_id=project_id, status=status, phase_id=phase_id, limit=limit, offset=offset
        ),
    )


@router.get("/projects/{project_id}/decisions")
def list_decisions(
    project_id: str,
    phase_id: Optional[str] = None,
    limit: int = Query(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS),
    offset: int = Query(default=0, ge=0),
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.list_decisions,
        read_tools.ListPhaseScopedArgs(
            project_id=project_id, phase_id=phase_id, limit=limit, offset=offset
        ),
    )


@router.get("/projects/{project_id}/risks")
def list_risks(
    project_id: str,
    phase_id: Optional[str] = None,
    limit: int = Query(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS),
    offset: int = Query(default=0, ge=0),
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.list_risks,
        read_tools.ListPhaseScopedArgs(
            project_id=project_id, phase_id=phase_id, limit=limit, offset=offset
        ),
    )


@router.get("/projects/{project_id}/docs")
def list_docs(
    project_id: str,
    limit: int = Query(default=MAX_LIST_ROWS, ge=1, le=MAX_LIST_ROWS),
    offset: int = Query(default=0, ge=0),
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.list_docs,
        read_tools.ListScopedArgs(project_id=project_id, limit=limit, offset=offset),
    )


@router.get("/docs/{doc_id}/excerpt")
def doc_excerpt(
    doc_id: str,
    max_chars: int = Query(default=MAX_DOC_EXCERPT_CHARS, ge=1, le=MAX_DOC_EXCERPT_CHARS),
    offset: int = Query(default=0, ge=0),
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.get_doc_excerpt,
        read_tools.DocExcerptArgs(doc_id=doc_id, max_chars=max_chars, offset=offset),
    )


@router.get("/approvals/{approval_id}/status")
def approval_status(
    approval_id: str,
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    return _run_read(
        session, cap, read_tools.get_approval_status,
        read_tools.ApprovalStatusArgs(approval_id=approval_id),
    )


@router.get("/projects/{project_id}/approvals/pending-count")
def pending_approval_count(
    project_id: str,
    cap: Capability = Depends(require_external_read),
    session: Session = Depends(get_session),
) -> dict:
    """#108: what the browser-extension badge polls."""
    return _run_read(
        session, cap, read_tools.get_pending_approval_count,
        read_tools.ProjectArgs(project_id=project_id),
    )


# --- proposal routes (require can_propose) -----------------------------------


@router.post("/proposals/task", status_code=202)
async def propose_task(
    request: Request,
    cap: Capability = Depends(require_external_propose),
    session: Session = Depends(get_session),
) -> dict:
    args = await _parse_json_body(request, propose_tools.CreateTaskProposalArgs)
    return _run_propose(session, cap, propose_tools.create_task_proposal, args)


@router.post("/proposals/task/{task_id}", status_code=202)
async def propose_task_update(
    task_id: str,
    request: Request,
    cap: Capability = Depends(require_external_propose),
    session: Session = Depends(get_session),
) -> dict:
    body = await _parse_json_body(request, _TaskUpdateBody)
    args = propose_tools.UpdateTaskProposalArgs(task_id=task_id, **body.model_dump())
    return _run_propose(session, cap, propose_tools.update_task_proposal, args)


@router.post("/proposals/decision", status_code=202)
async def propose_decision(
    request: Request,
    cap: Capability = Depends(require_external_propose),
    session: Session = Depends(get_session),
) -> dict:
    args = await _parse_json_body(request, propose_tools.CreateDecisionProposalArgs)
    return _run_propose(session, cap, propose_tools.create_decision_proposal, args)


def _assert_safe_routes() -> None:
    for route in router.routes:
        path = getattr(route, "path", "").lower()
        bad = [s for s in _FORBIDDEN_PATH_SUBSTRINGS if s in path]
        assert not bad, f"forbidden substring in external route {path!r}: {bad}"


_assert_safe_routes()
