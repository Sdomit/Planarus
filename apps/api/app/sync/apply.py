"""Apply a resolved sync plan between two replicas (Phase 10.6b).

Given a conflict-free ``SyncPlan``, propagate each change so the two databases
converge: one-sided creates/updates are copied from the side that changed to the
side that didn't; deletes are removed from the lagging side. Records are copied by
value (all columns) via ``Session.merge`` (upsert by primary key). Creates/updates
are applied parents-before-children and deletes children-before-parents so foreign
keys always resolve.

Transport (moving records between *machines*) is still out of scope — this applies
between two SQLAlchemy sessions in one process. It is the piece that makes a
resolved plan actually take effect.
"""
from __future__ import annotations

from sqlmodel import Session

from app.models.project import Project
from app.sync.diff import Change, SyncPlan
from app.sync.manifest import _SYNC_MODELS

# entity_type → model, and a parent-before-child ordering (project first, then the
# manifest's declared order, which already lists parents before children).
_TYPE_MODEL = {"project": Project, **{m.__tablename__: m for m in _SYNC_MODELS}}
_ORDER = ["project", *(m.__tablename__ for m in _SYNC_MODELS)]


def _row_values(row) -> dict:
    return {col.name: getattr(row, col.name) for col in row.__table__.columns}


def _apply_changes(source: Session, target: Session, changes: list[Change]) -> None:
    """Copy source→target for each change: create/update via merge, delete by id."""
    upserts = [c for c in changes if not c.kind.value.endswith("_delete")]
    deletes = [c for c in changes if c.kind.value.endswith("_delete")]

    for change in sorted(upserts, key=lambda c: _ORDER.index(c.key[0])):
        entity_type, entity_id = change.key
        model = _TYPE_MODEL[entity_type]
        src_row = source.get(model, entity_id)
        if src_row is not None:  # source may have deleted it concurrently
            target.merge(model(**_row_values(src_row)))

    for change in sorted(deletes, key=lambda c: _ORDER.index(c.key[0]), reverse=True):
        entity_type, entity_id = change.key
        model = _TYPE_MODEL[entity_type]
        tgt_row = target.get(model, entity_id)
        if tgt_row is not None:
            target.delete(tgt_row)

    target.commit()


def apply_plan(local: Session, remote: Session, plan: SyncPlan) -> None:
    """Make ``local`` and ``remote`` converge per a conflict-free plan.

    Raises ``ValueError`` if any conflict remains unresolved — a plan is never
    applied with open conflicts (resolve them via ``resolve_conflicts`` first).
    """
    if plan.has_conflicts:
        raise ValueError(
            "plan has unresolved conflicts; resolve them before applying"
        )
    # local_* changes originate on local → push to remote; remote_* → pull to local.
    _apply_changes(local, remote, plan.to_remote())
    _apply_changes(remote, local, plan.to_local())
