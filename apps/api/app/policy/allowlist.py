"""Static, versioned action allowlist for approval proposals (Phase 7A).

The allowlist is the ONLY thing that grants a proposal power. It is code, not
data, and is pinned by ``POLICY_VERSION`` — a proposal bound to an old policy
version is invalidated at apply time. Keep ``ACTION_POLICIES`` keys in sync with
``app.core.constants.APPROVAL_ACTION_TYPES`` (asserted at import below).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.core.constants import (
    APPROVAL_ACTION_TYPES,
    TASK_PRIORITIES,
)
from app.core.exceptions import PolicyError

POLICY_VERSION: int = 1

# Default hard cap on the serialized patch to bound memory/DoS. Small string
# patches (task/decision) never need more than this.
MAX_PATCH_BYTES: int = 64 * 1024
# Phase 13c: a canvas is a Doc whose content_json (Excalidraw scene) is capped at
# 2 MiB server-side; the doc.update patch adds markdown_cache + JSON framing, so
# allow headroom above that single-field limit.
DOC_UPDATE_MAX_PATCH_BYTES: int = 3 * 1024 * 1024

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
    # Fields whose value is an internal canonical entity reference (not free text).
    # A reference field is exempt from secret scanning ONLY after it is validated as
    # an existing, project-owned reference for this exact proposal (never by prefix
    # or entropy). Must be a subset of allowed_fields (asserted at import).
    reference_fields: frozenset[str] = frozenset()
    # Per-action serialized-patch ceiling. Defaults to the small-string cap; only
    # doc.update (large canvas scenes) raises it.
    max_patch_bytes: int = MAX_PATCH_BYTES


ACTION_POLICIES: dict[str, ActionPolicy] = {
    "task.create": ActionPolicy(
        action_type="task.create",
        target_entity_type="task",
        is_create=True,
        allowed_fields=frozenset(
            {"title", "description", "status", "priority", "phase_id", "stage_id", "due_at"}
        ),
        required_fields=frozenset({"title"}),
        reference_fields=frozenset({"phase_id", "stage_id"}),
    ),
    "task.update": ActionPolicy(
        action_type="task.update",
        target_entity_type="task",
        is_create=False,
        allowed_fields=frozenset(
            {"title", "description", "status", "priority", "phase_id", "stage_id", "due_at"}
        ),
        required_fields=frozenset(),
        reference_fields=frozenset({"phase_id", "stage_id"}),
    ),
    "decision.create": ActionPolicy(
        action_type="decision.create",
        target_entity_type="decision",
        is_create=True,
        allowed_fields=frozenset({"title", "context", "decision", "status"}),
        required_fields=frozenset({"title", "decision"}),
        reference_fields=frozenset(),
    ),
    # Phase 13c: AI-proposed canvas/doc content edits. content_json is the new
    # scene (secret-scanned like any free text); markdown_cache is optional derived
    # text. No reference fields; the base-target fingerprint over content_json is
    # what makes a stale proposal (human edited the canvas meanwhile) fail closed.
    "doc.update": ActionPolicy(
        action_type="doc.update",
        target_entity_type="doc",
        is_create=False,
        allowed_fields=frozenset({"content_json", "markdown_cache"}),
        required_fields=frozenset({"content_json"}),
        reference_fields=frozenset(),
        max_patch_bytes=DOC_UPDATE_MAX_PATCH_BYTES,
    ),
}

# Fail fast if the DB CHECK list and the field policy ever drift.
assert set(ACTION_POLICIES) == set(
    APPROVAL_ACTION_TYPES
), "ACTION_POLICIES must match APPROVAL_ACTION_TYPES"

# A reference field must be part of its action's schema. This keeps the scan-exempt
# set (validated reference fields) bounded by the declared, allowlisted fields.
for _action, _policy in ACTION_POLICIES.items():
    assert (
        _policy.reference_fields <= _policy.allowed_fields
    ), f"reference_fields must be a subset of allowed_fields for {_action}"

_TASK_PRIORITIES = frozenset(TASK_PRIORITIES)
# Task statuses are open-ended (Phase 15.5 custom statuses); only the slug shape
# is checked here — the project-scoped set is enforced at apply time.
_STATUS_SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")


def get_policy(action_type: str) -> ActionPolicy:
    policy = ACTION_POLICIES.get(action_type)
    if policy is None:
        raise PolicyError(f"unknown action type: {action_type!r}")
    return policy


def _validate_enums(action_type: str, patch: dict) -> None:
    status = patch.get("status")
    if status is not None:
        # Phase 15.5: task AND decision statuses allow custom values. The policy
        # layer is project-agnostic, so it only checks slug shape here; the
        # concrete per-project set (built-ins ∪ custom) is enforced at apply time
        # by the entity's apply handler.
        if not _STATUS_SLUG.match(status):
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

    if action_type == "doc.update":
        # content_json is the canonical scene; a malformed body would apply an
        # unopenable canvas. Validate structure (not size — that is the caller's cap).
        try:
            json.loads(normalized["content_json"])
        except (ValueError, TypeError):
            raise PolicyError("content_json must be valid JSON")

    return normalized
