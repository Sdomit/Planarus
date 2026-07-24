"""Project sync manifest (Phase 10.6).

A manifest maps each syncable entity in a project to a **content signature** — a
SHA-256 over its column values excluding the volatile ``created_at``/``updated_at``
timestamps. Excluding timestamps means two replicas that made the *same* edit
produce the *same* signature (convergent, no false conflict), and a timestamp-only
touch doesn't register as a change. Comparing two manifests reveals exactly which
entities differ, without reading their full contents.
"""
from __future__ import annotations

import json

from sqlmodel import Session

from app.core.utils import sha256_hex
from app.models.project import Project
from app.services import project_graph

# Key: (entity_type, entity_id). Value: content signature.
Manifest = dict[tuple[str, str], str]

# Fields that change on every write and must not affect the content signature.
_VOLATILE = {"created_at", "updated_at"}

# The models this engine syncs, parents first — read from the one graph
# description shared with duplicate and export/import (#87), rather than a third
# hand-maintained list that drifts from them. The project row itself is added
# separately. Task-scoped rows (checklist items) reach the project through their
# parent tasks, which ``project_graph.manifest_rows`` handles.
_SYNC_MODELS = tuple(e.model for e in project_graph.entities_for("manifest"))


def entity_signature(row) -> str:
    """SHA-256 of a row's non-volatile column values (stable, order-independent)."""
    data = {
        col.name: getattr(row, col.name)
        for col in row.__table__.columns
        if col.name not in _VOLATILE
    }
    return sha256_hex(json.dumps(data, sort_keys=True, default=str))


def build_manifest(session: Session, project_id: str) -> Manifest:
    """Build the content manifest for one project's syncable entities."""
    manifest: Manifest = {}
    project = session.get(Project, project_id)
    if project is not None:
        manifest[("project", project.id)] = entity_signature(project)
    for table, row in project_graph.manifest_rows(session, project_id):
        manifest[(table, row.id)] = entity_signature(row)
    return manifest
