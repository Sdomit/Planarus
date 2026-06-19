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
from app.fsmemory.regenerator import RegenReport
from app.fsmemory.renderers import RenderContext, render
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


def _content_updated_at(project: Project, workspace: Workspace) -> str:
    return max(project.updated_at, workspace.updated_at)


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


def read_content(
    session: Session, context_file: ContextFile
) -> tuple[Optional[str], bool]:
    """Return (on-disk content, drifted). Content is None if the file is absent."""
    project = session.get(Project, context_file.project_id)
    if project is None or not project.folder_path:
        return None, False
    content = atomic_io.read_text(project.folder_path, context_file.relative_path)
    if content is None:
        return None, False
    on_disk_sum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return content, on_disk_sum != context_file.checksum


def compute_diff(session: Session, context_file: ContextFile) -> str:
    """Unified diff of on-disk content vs. what regeneration would render now."""
    project = session.get(Project, context_file.project_id)
    if project is None or not project.folder_path:
        return ""
    workspace = session.get(Workspace, project.workspace_id)
    spec = _spec_for(context_file.relative_path)
    if workspace is None or spec is None:
        return ""
    ctx = RenderContext(project, workspace, _content_updated_at(project, workspace))
    rendered = render(spec, ctx)
    on_disk = atomic_io.read_text(project.folder_path, context_file.relative_path) or ""
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
