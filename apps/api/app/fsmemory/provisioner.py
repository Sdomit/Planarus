"""Project folder provisioning: the directory tree and `.agentboard/` mirrors.

The DB is authoritative; the `.agentboard/*.json` files are portable mirrors and
the reserved directories are empty working space. JSON mirrors are written only
when their content changes, so provisioning is idempotent.
"""
from __future__ import annotations

import json
import os

from app.fsmemory import atomic_io
from app.fsmemory.path_safety import resolve_root, safe_makedirs
from app.fsmemory.spec import AGENTBOARD_DIR, AUDIT_LOG_RELPATH, CONTEXT_DIR, RESERVED_DIRS
from app.models.project import Project
from app.models.workspace import Workspace


def _json_text(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _project_mirror(project: Project) -> dict:
    return {
        "id": project.id,
        "workspace_id": project.workspace_id,
        "title": project.title,
        "slug": project.slug,
        "summary": project.summary,
        "project_type": project.project_type,
        "status": project.status,
        "priority": project.priority,
        "folder_path": project.folder_path,
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "archived_at": project.archived_at,
    }


def _workspace_link(workspace: Workspace) -> dict:
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "workspace_slug": workspace.slug,
        "default_project_root": workspace.default_project_root,
    }


def _settings() -> dict:
    return {
        "schema_version": 1,
        "generation": {
            "auto_regenerate_on_save": True,
            "line_endings": "lf",
        },
        "tokens": {
            "context_pack_budget": 4000,
        },
    }


def provision_tree(root: str, project: Project, workspace: Workspace) -> None:
    """Create the folder tree and write/refresh the `.agentboard/` mirrors."""
    root_real = resolve_root(root)
    os.makedirs(root_real, exist_ok=True)

    safe_makedirs(root, AGENTBOARD_DIR)
    safe_makedirs(root, CONTEXT_DIR)
    for rel_dir in RESERVED_DIRS:
        safe_makedirs(root, rel_dir)

    atomic_io.write_text_if_changed(
        root, f"{AGENTBOARD_DIR}/project.json", _json_text(_project_mirror(project))
    )
    atomic_io.write_text_if_changed(
        root, f"{AGENTBOARD_DIR}/workspace-link.json", _json_text(_workspace_link(workspace))
    )
    atomic_io.write_text_if_changed(
        root, f"{AGENTBOARD_DIR}/settings.json", _json_text(_settings())
    )
    atomic_io.ensure_file(root, AUDIT_LOG_RELPATH)
