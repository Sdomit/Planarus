"""Cross-machine sync transport (Phase 10.6c).

P10.6b's `apply_plan` converges two SQLAlchemy sessions in one process. To sync
*across machines* (a local replica ↔ a hosted one) the state has to travel as
data, not live ORM objects. This module provides that:

- `build_snapshot(session, project_id)` → a JSON-safe `{manifest, records}` a
  replica publishes (what it currently holds).
- `import_change_set(session, changes, records)` → apply a change set to *this*
  database from serialized records (FK-safe order), the cross-machine analogue of
  `apply._apply_changes`. Used by the receiver of a push and by a client applying
  a pulled remote's changes locally.

The typical flow (client drives): pull the remote snapshot → three-way diff
against the stored baseline and the local manifest → apply the remote's one-sided
changes locally → push the local's one-sided changes to the remote → save the new
baseline. Conflicts stop the flow for explicit resolution (P10.6). The HTTP
endpoints that expose snapshot/push live in `api/v1/endpoints/sync.py`.
"""
from __future__ import annotations

from sqlmodel import Session

from app.sync.apply import _ORDER, _TYPE_MODEL, _row_values
from app.sync.diff import Change, ChangeKind
from app.sync.manifest import Manifest, build_manifest

EntityKey = tuple[str, str]


def key_str(key: EntityKey) -> str:
    return f"{key[0]}::{key[1]}"


def parse_key(s: str) -> EntityKey:
    entity_type, entity_id = s.split("::", 1)
    return (entity_type, entity_id)


def export_records(session: Session, keys: list[EntityKey]) -> dict[str, dict]:
    """Serialize the given entities to ``{key_str: {column: value}}`` (JSON-safe —
    every synced column is a str/int/bool/None)."""
    out: dict[str, dict] = {}
    for key in keys:
        model = _TYPE_MODEL.get(key[0])
        if model is None:
            continue
        row = session.get(model, key[1])
        if row is not None:
            out[key_str(key)] = _row_values(row)
    return out


def build_snapshot(session: Session, project_id: str) -> dict:
    """A replica's publishable state for a project: its manifest + all records."""
    manifest = build_manifest(session, project_id)
    return {
        "project_id": project_id,
        "manifest": [[t, i, sig] for (t, i), sig in sorted(manifest.items())],
        "records": export_records(session, list(manifest.keys())),
    }


def snapshot_manifest(snapshot: dict) -> Manifest:
    """Reconstruct the manifest dict from a snapshot payload."""
    return {(t, i): sig for t, i, sig in snapshot["manifest"]}


class ScopeViolation(Exception):
    """A pushed change references an entity outside the target project (a
    cross-tenant write attempt). Nothing is applied."""


def _record_in_project(entity_type: str, record: dict, project_id: str) -> bool:
    if entity_type == "project":
        return record.get("id") == project_id
    return record.get("project_id") == project_id


def _row_in_project(entity_type: str, row, project_id: str) -> bool:
    if entity_type == "project":
        return getattr(row, "id", None) == project_id
    return getattr(row, "project_id", None) == project_id


def import_change_set(
    session: Session,
    changes: list[Change],
    records: dict[str, dict],
    restrict_project_id: str | None = None,
) -> None:
    """Apply ``changes`` to this database using serialized ``records``.

    Creates/updates upsert the provided record by primary key (parents first);
    deletes remove by id (children first). Missing records for an upsert are
    skipped (the sender may have re-deleted concurrently). One commit at the end.

    When ``restrict_project_id`` is set (always, for pushes over the wire), every
    change is validated to belong to that project **before anything is applied** —
    a payload that references another project raises ``ScopeViolation`` and nothing
    is written. This is the boundary that stops a push from injecting cross-tenant
    records. In-process callers (``apply_plan``) trust their own sessions and omit it.
    """
    upserts = [c for c in changes if not c.kind.value.endswith("_delete")]
    deletes = [c for c in changes if c.kind.value.endswith("_delete")]

    if restrict_project_id is not None:
        for change in upserts:
            record = records.get(key_str(change.key))
            if record is not None and not _record_in_project(
                change.key[0], record, restrict_project_id
            ):
                raise ScopeViolation(f"{key_str(change.key)} is not in this project")
        for change in deletes:
            row = session.get(_TYPE_MODEL[change.key[0]], change.key[1])
            if row is not None and not _row_in_project(
                change.key[0], row, restrict_project_id
            ):
                raise ScopeViolation(f"{key_str(change.key)} is not in this project")

    for change in sorted(upserts, key=lambda c: _ORDER.index(c.key[0])):
        record = records.get(key_str(change.key))
        if record is not None:
            session.merge(_TYPE_MODEL[change.key[0]](**record))

    for change in sorted(deletes, key=lambda c: _ORDER.index(c.key[0]), reverse=True):
        model = _TYPE_MODEL[change.key[0]]
        row = session.get(model, change.key[1])
        if row is not None:
            session.delete(row)

    session.commit()
