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
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import sha256_hex
from app.models.blocker import Blocker
from app.models.comment import Comment
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.link import Link
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task

# Key: (entity_type, entity_id). Value: content signature.
Manifest = dict[tuple[str, str], str]

# Fields that change on every write and must not affect the content signature.
_VOLATILE = {"created_at", "updated_at"}

# Project-scoped models synced by this engine (each carries ``project_id``). The
# project row itself is added separately. checklist items (task-scoped) are a
# documented follow-on.
_SYNC_MODELS = (
    Phase,
    Stage,
    Task,
    Decision,
    Risk,
    Blocker,
    Milestone,
    Doc,
    Comment,
    Link,
)


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
    for model in _SYNC_MODELS:
        rows = session.exec(
            select(model).where(model.project_id == project_id)
        ).all()
        for row in rows:
            manifest[(model.__tablename__, row.id)] = entity_signature(row)
    return manifest
