"""Static, versioned action allowlist for approval proposals (Phase 7A).

The allowlist is the ONLY thing that grants a proposal power. It is code, not
data, and is pinned by ``POLICY_VERSION`` — a proposal bound to an old policy
version is invalidated at apply time. Keep ``ACTION_POLICIES`` keys in sync with
``app.core.constants.APPROVAL_ACTION_TYPES`` (asserted at import below).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.constants import (
    APPROVAL_ACTION_TYPES,
    DECISION_STATUSES,
    TASK_PRIORITIES,
    TASK_STATUSES,
)
from app.core.errors import PolicyError

POLICY_VERSION: int = 1

# Hard cap on the serialized patch to bound memory/DoS. The Phase 7A allowlist
# carries no large-content action (doc updates are deferred), so 64 KiB is ample.
MAX_PATCH_BYTES: int = 64 * 1024

# Never accept these from a proposer for ANY action — server/identity owned.
GLOBAL_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "project_id",
        "workspace_id",
        "created_at",
        "updated_at",
        "sort_order",
        "version",
        "archived_at",
        "deleted_at",
        "export_relative_path",
        "export_checksum",
        "exported_at",
    }
)


@dataclass(frozen=True)
class ActionPolicy:
    action_type: str
    target_entity_type: str  # "task" | "decision"
    is_create: bool
    allowed_fields: frozenset[str]
    required_fields: frozenset[str]


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "task.create": ActionPolicy(
        action_type="task.create",
        target_entity_type="task",
        is_create=True,
        allowed_fields=frozenset(
            {"title", "description", "status", "priority", "phase_id", "stage_id", "due_at"}
        ),
        required_fields=frozenset({"title"}),
    ),
    "task.update": ActionPolicy(
        action_type="task.update",
        target_entity_type="task",
        is_create=False,
        allowed_fields=frozenset(
            {"title", "description", "status", "priority", "phase_id", "stage_id", "due_at"}
        ),
        required_fields=frozenset(),
    ),
    "decision.create": ActionPolicy(
        action_type="decision.create",
        target_entity_type="decision",
        is_create=True,
        allowed_fields=frozenset({"title", "context", "decision", "status"}),
        required_fields=frozenset({"title", "decision"}),
    ),
}

# Fail fast if the DB CHECK list and the field policy ever drift.
assert set(ACTION_POLICIES) == set(
    APPROVAL_ACTION_TYPES
), "ACTION_POLICIES must match APPROVAL_ACTION_TYPES"

_TASK_STATUSES = frozenset(TASK_STATUSES)
_TASK_PRIORITIES = frozenset(TASK_PRIORITIES)
_DECISION_STATUSES = frozenset(DECISION_STATUSES)


def get_policy(action_type: str) -> ActionPolicy:
    policy = ACTION_POLICIES.get(action_type)
    if policy is None:
        raise PolicyError(f"unknown action type: {action_type!r}")
    return policy


def _validate_enums(action_type: str, patch: dict) -> None:
    status = patch.get("status")
    if status is not None:
        valid = _TASK_STATUSES if action_type.startswith("task.") else _DECISION_STATUSES
        if status not in valid:
            raise PolicyError(f"invalid status value for {action_type}")
    priority = patch.get("priority")
    if priority is not None and priority not in _TASK_PRIORITIES:
        raise PolicyError("invalid priority value")


def normalize_patch(action_type: str, patch: dict) -> dict:
    """Validate a raw proposed patch and return a normalized, allowlisted copy.

    Raises PolicyError on unknown/forbidden fields, missing required fields, bad
    enum values, non-string values, or blank required text. Never mutates input.
    """
    if not isinstance(patch, dict):
        raise PolicyError("patch must be an object")
    policy = get_policy(action_type)

    keys = set(patch.keys())
    forbidden = keys & GLOBAL_FORBIDDEN_FIELDS
    if forbidden:
        raise PolicyError(f"forbidden field(s): {', '.join(sorted(forbidden))}")
    unknown = keys - policy.allowed_fields
    if unknown:
        raise PolicyError(
            f"unknown field(s) for {action_type}: {', '.join(sorted(unknown))}"
        )
    missing = policy.required_fields - keys
    if missing:
        raise PolicyError(f"missing required field(s): {', '.join(sorted(missing))}")

    normalized: dict = {}
    for key in sorted(keys):
        value = patch[key]
        if value is not None and not isinstance(value, str):
            # Every Phase 7A allowed field is free-text (string) or null.
            raise PolicyError(f"field {key!r} must be a string or null")
        normalized[key] = value

    _validate_enums(action_type, normalized)

    for required in sorted(policy.required_fields):
        value = normalized.get(required)
        if not isinstance(value, str) or not value.strip():
            raise PolicyError(f"field {required!r} must not be blank")

    return normalized
