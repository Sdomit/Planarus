"""Persist and load a project's last-synced manifest (Phase 10.6b).

The manifest dict (``{(entity_type, id): signature}``) is serialized as a sorted
list of ``[entity_type, id, signature]`` triples so it round-trips through JSON
(dict tuple-keys aren't JSON-encodable) and is stable/diffable.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.sync_baseline import SyncBaseline
from app.sync.manifest import Manifest


def _dump(manifest: Manifest) -> str:
    return json.dumps(
        sorted([entity_type, entity_id, sig] for (entity_type, entity_id), sig in manifest.items())
    )


def _parse(raw: str) -> Manifest:
    return {(t, i): sig for t, i, sig in json.loads(raw)}


def load_baseline(session: Session, project_id: str) -> Optional[Manifest]:
    """The stored last-sync manifest for a project, or None if never synced."""
    row = session.exec(
        select(SyncBaseline).where(SyncBaseline.project_id == project_id)
    ).first()
    return _parse(row.manifest_json) if row is not None else None


def save_baseline(session: Session, project_id: str, manifest: Manifest) -> None:
    """Upsert the last-sync manifest for a project (one row per project)."""
    row = session.exec(
        select(SyncBaseline).where(SyncBaseline.project_id == project_id)
    ).first()
    if row is None:
        row = SyncBaseline(
            id=new_id("syncb"),
            project_id=project_id,
            manifest_json=_dump(manifest),
            updated_at=now_utc(),
        )
    else:
        row.manifest_json = _dump(manifest)
        row.updated_at = now_utc()
    session.add(row)
    session.commit()
