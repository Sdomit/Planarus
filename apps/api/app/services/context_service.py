"""Service layer for the generated context pack (human-local operations only).

No external AI write surface, MCP, or approval queue here — those are later
phases. Reads resolve by `ContextFile` identity (stored `relative_path`) through
the path-safety layer, never a raw caller-supplied path.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import now_utc
from app.fsmemory import atomic_io, regenerate
from app.fsmemory.project_root import resolve_project_root_or_none
from app.fsmemory.regenerator import RegenReport, build_render_context
from app.fsmemory.renderers import render
from app.fsmemory.spec import CONTEXT_FILES, ContextFileSpec
from app.models.context_file import ContextFile
from app.models.project import Project
from app.models.workspace import Workspace
from app.services.audit_service import create_audit_event


def _spec_for(relative_path: str) -> Optional[ContextFileSpec]:
    for spec in CONTEXT_FILES:
        if spec.relative_path == relative_path:
            return spec
    return None


def list_context_files(session: Session, project_id: str) -> list[ContextFile]:
    stmt = (
        select(ContextFile)
        .where(ContextFile.project_id == project_id)
        .order_by(ContextFile.relative_path)
    )
    return list(session.exec(stmt).all())


def get_context_file(session: Session, context_file_id: str) -> Optional[ContextFile]:
    return session.get(ContextFile, context_file_id)


def set_pinned(
    session: Session, context_file_id: str, pinned: bool
) -> Optional[ContextFile]:
    cf = session.get(ContextFile, context_file_id)
    if cf is None:
        return None
    cf.pinned = pinned
    cf.updated_at = now_utc()
    session.add(cf)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="context_file",
        entity_id=cf.id,
        project_id=cf.project_id,
        payload_json=json.dumps({"pinned": pinned}),
    )
    session.commit()
    session.refresh(cf)
    return cf


def adopt_on_disk(
    session: Session, context_file_id: str
) -> tuple[Optional[ContextFile], str]:
    """Accept the current on-disk content as the file's recorded state.

    Returns (row, status) where status is one of ok | not-found | no-root |
    missing-on-disk.

    Adoption **pins**. All three governance files ship `authored=False`, so they
    are generated and unpinned by default — and once the checksum matches the
    on-disk bytes, an unpinned row falls through regeneration's final branch and
    gets overwritten with the starter scaffold. Adopting without pinning would
    therefore clear the drift and then silently destroy the very edit it just
    accepted, on the next regeneration. Pinning is what makes "I meant this"
    stick (#98).

    Without this action, drift was a one-way door: the only other checksum writer
    is that overwrite branch, so the sole way to clear drift was to discard the
    hand edits it was recording.
    """
    cf = session.get(ContextFile, context_file_id)
    if cf is None:
        return None, "not-found"
    project = session.get(Project, cf.project_id)
    if project is None:
        return None, "not-found"
    root = resolve_project_root_or_none(project)  # recheck-before-op (#115)
    if root is None:
        return cf, "no-root"
    content = atomic_io.read_text(root, cf.relative_path)
    if content is None:
        return cf, "missing-on-disk"

    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    already = checksum == cf.checksum
    was_pinned = bool(cf.pinned)
    cf.checksum = checksum
    cf.pinned = True
    cf.token_estimate = max(1, len(content.encode("utf-8")) // 4)
    cf.last_manual_edit_at = now_utc()
    cf.updated_at = now_utc()
    session.add(cf)
    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="context_file",
        entity_id=cf.id,
        project_id=cf.project_id,
        # The checksum is the whole point of the action, so it goes in the record.
        # No content: an audit payload is not a place to copy a file body.
        payload_json=json.dumps(
            {
                "adopted_checksum": checksum,
                "was_already_in_sync": already,
                "pinned_by_adoption": not was_pinned,
            }
        ),
    )
    session.commit()
    session.refresh(cf)
    return cf, "ok"


def read_content(
    session: Session, context_file: ContextFile
) -> tuple[Optional[str], bool]:
    """Return (on-disk content, drifted). Content is None if the file is absent."""
    project = session.get(Project, context_file.project_id)
    if project is None:
        return None, False
    root = resolve_project_root_or_none(project)  # recheck-before-op (#115)
    if root is None:
        return None, False
    content = atomic_io.read_text(root, context_file.relative_path)
    if content is None:
        return None, False
    on_disk_sum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, on_disk_sum != context_file.checksum


def compute_diff(session: Session, context_file: ContextFile) -> str:
    """Unified diff of on-disk content vs. what regeneration would render now."""
    project = session.get(Project, context_file.project_id)
    if project is None:
        return ""
    root = resolve_project_root_or_none(project)  # recheck-before-op (#115)
    if root is None:
        return ""
    workspace = session.get(Workspace, project.workspace_id)
    spec = _spec_for(context_file.relative_path)
    if workspace is None or spec is None:
        return ""
    ctx = build_render_context(session, project, workspace)
    rendered = render(spec, ctx)
    on_disk = atomic_io.read_text(root, context_file.relative_path) or ""
    rel = context_file.relative_path
    diff = difflib.unified_diff(
        on_disk.splitlines(keepends=True),
        rendered.splitlines(keepends=True),
        fromfile=f"a/{rel}",
        tofile=f"b/{rel}",
    )
    return "".join(diff)


def provision_and_regenerate(
    session: Session, project: Project, *, actor_type: str = "human"
) -> RegenReport:
    """Provision the folder + regenerate the pack, then commit. Raises on failure."""
    workspace = session.get(Workspace, project.workspace_id)
    if workspace is None:
        raise ValueError(f"workspace '{project.workspace_id}' not found")
    report = regenerate(session, project, workspace, actor_type=actor_type)
    session.commit()
    return report
