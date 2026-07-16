"""Three-way sync diff with explicit conflict detection (Phase 10.6).

Given the last-synced **base** manifest and the current **local** and **remote**
manifests, classify every entity. The defining rule: when *both* sides changed an
entity away from the base in different ways, it is a **conflict** that a human must
resolve — never a silent last-write-wins. One-sided changes propagate to the other
replica; convergent changes (both sides identical) are no-ops.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.sync.manifest import Manifest

EntityKey = tuple[str, str]


class ChangeKind(str, Enum):
    LOCAL_CREATE = "local_create"
    LOCAL_UPDATE = "local_update"
    LOCAL_DELETE = "local_delete"
    REMOTE_CREATE = "remote_create"
    REMOTE_UPDATE = "remote_update"
    REMOTE_DELETE = "remote_delete"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class Change:
    key: EntityKey
    kind: ChangeKind


@dataclass
class SyncPlan:
    changes: list[Change] = field(default_factory=list)

    @property
    def conflicts(self) -> list[Change]:
        return [c for c in self.changes if c.kind is ChangeKind.CONFLICT]

    @property
    def has_conflicts(self) -> bool:
        return any(c.kind is ChangeKind.CONFLICT for c in self.changes)

    def to_local(self) -> list[Change]:
        """Non-conflict changes that must be applied to the LOCAL replica."""
        return [c for c in self.changes if c.kind.value.startswith("remote_")]

    def to_remote(self) -> list[Change]:
        """Non-conflict changes that must be applied to the REMOTE replica."""
        return [c for c in self.changes if c.kind.value.startswith("local_")]


def _one_sided_kind(base_sig, side_sig, prefix: str) -> ChangeKind:
    if base_sig is None:
        return ChangeKind[f"{prefix}_CREATE"]
    if side_sig is None:
        return ChangeKind[f"{prefix}_DELETE"]
    return ChangeKind[f"{prefix}_UPDATE"]


def three_way_diff(base: Manifest, local: Manifest, remote: Manifest) -> SyncPlan:
    plan = SyncPlan()
    for key in sorted(set(base) | set(local) | set(remote)):
        b: Optional[str] = base.get(key)
        loc: Optional[str] = local.get(key)
        rem: Optional[str] = remote.get(key)

        if loc == rem:
            continue  # both replicas agree (convergent or both unchanged)

        local_changed = loc != b
        remote_changed = rem != b

        if local_changed and remote_changed:
            plan.changes.append(Change(key, ChangeKind.CONFLICT))
        elif local_changed:
            plan.changes.append(Change(key, _one_sided_kind(b, loc, "LOCAL")))
        else:  # remote_changed
            plan.changes.append(Change(key, _one_sided_kind(b, rem, "REMOTE")))
    return plan


def resolve_conflicts(
    plan: SyncPlan, choices: dict[EntityKey, str]
) -> SyncPlan:
    """Return a new plan with each conflict replaced by the chosen side.

    ``choices`` maps a conflicting entity key to ``"local"`` or ``"remote"``. Every
    conflict MUST have an explicit choice — an unresolved conflict raises, so a plan
    can never be silently applied with conflicts still open. A local win becomes a
    ``LOCAL_UPDATE`` (apply local → remote); a remote win a ``REMOTE_UPDATE``.
    """
    resolved: list[Change] = []
    for change in plan.changes:
        if change.kind is not ChangeKind.CONFLICT:
            resolved.append(change)
            continue
        pick = choices.get(change.key)
        if pick == "local":
            resolved.append(Change(change.key, ChangeKind.LOCAL_UPDATE))
        elif pick == "remote":
            resolved.append(Change(change.key, ChangeKind.REMOTE_UPDATE))
        else:
            raise ValueError(f"unresolved conflict for {change.key}: choose local/remote")
    return SyncPlan(resolved)
