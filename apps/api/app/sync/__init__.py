"""Sync foundation — change detection + conflict planning (Phase 10.6).

Sync is the hardest, deliberately-last piece. This slice ships its **core**: a
content-based *manifest* of a project's entities, and a *three-way diff* that
classifies every change and, crucially, **surfaces conflicts for explicit
resolution instead of silently applying last-write-wins**.

Transport, the last-sync baseline and plan application were future work when this
was written; all three shipped (P10.6b/P10.6c) and are re-exported below.

Off by default, but no longer unreachable: `app/api/v1/endpoints/sync.py` wires
the manifest to a local route. Importing this package still changes nothing about
the running app.
"""
from app.sync.apply import apply_plan
from app.sync.baseline import load_baseline, save_baseline
from app.sync.diff import (
    Change,
    ChangeKind,
    SyncPlan,
    resolve_conflicts,
    three_way_diff,
)
from app.sync.manifest import Manifest, build_manifest, entity_signature
from app.sync.transport import (
    ScopeViolation,
    build_snapshot,
    export_records,
    import_change_set,
    snapshot_manifest,
)

__all__ = [
    "Manifest",
    "build_manifest",
    "entity_signature",
    "Change",
    "ChangeKind",
    "SyncPlan",
    "three_way_diff",
    "resolve_conflicts",
    "apply_plan",
    "load_baseline",
    "save_baseline",
    "build_snapshot",
    "snapshot_manifest",
    "export_records",
    "import_change_set",
    "ScopeViolation",
]
