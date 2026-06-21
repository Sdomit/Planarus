"""Canonical domain constants shared across schemas, models, and validation.

Migrations intentionally do NOT import from here — a migration is a frozen
snapshot of the schema at authoring time, so it hardcodes its own value list.
Keep the migration's CHECK list in sync with the constant here by hand when a
new value is introduced (that change ships as a new migration revision).
"""


def _check_sql(column: str, values: tuple[str, ...]) -> str:
    vals = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({vals})"


def _nullable_check_sql(column: str, values: tuple[str, ...]) -> str:
    """CHECK expression for nullable enum columns — NULL is always allowed."""
    vals = ", ".join(f"'{v}'" for v in values)
    return f"{column} IS NULL OR {column} IN ({vals})"


# Project.status — see docs/plan/03-data-model.md "Enums (canonical values)".
PROJECT_STATUSES: tuple[str, ...] = (
    "idea",
    "researching",
    "planning",
    "ready",
    "active",
    "blocked",
    "paused",
    "later",
    "review",
    "done",
    "archived",
)


def project_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, PROJECT_STATUSES)


# Phase and Stage share the same lifecycle status values.
PHASE_STATUSES: tuple[str, ...] = (
    "planned",
    "active",
    "blocked",
    "done",
    "canceled",
)


def phase_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, PHASE_STATUSES)


# Task
TASK_STATUSES: tuple[str, ...] = (
    "backlog",
    "ready",
    "in_progress",
    "waiting",
    "needs_review",
    "blocked",
    "done",
    "canceled",
)

TASK_PRIORITIES: tuple[str, ...] = ("low", "med", "high", "urgent")


def task_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, TASK_STATUSES)


def task_priority_check_sql(column: str = "priority") -> str:
    return _nullable_check_sql(column, TASK_PRIORITIES)


# Decision
DECISION_STATUSES: tuple[str, ...] = (
    "proposed",
    "accepted",
    "superseded",
    "reversed",
)


def decision_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, DECISION_STATUSES)


# Risk
RISK_STATUSES: tuple[str, ...] = (
    "open",
    "monitoring",
    "mitigated",
    "accepted",
    "closed",
)

RISK_SEVERITIES: tuple[str, ...] = ("low", "medium", "high", "critical")


def risk_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, RISK_STATUSES)


def risk_severity_check_sql(column: str = "severity") -> str:
    return _check_sql(column, RISK_SEVERITIES)


# Blocker
BLOCKER_STATUSES: tuple[str, ...] = ("open", "resolved", "canceled")


def blocker_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, BLOCKER_STATUSES)


# Doc
DOC_TYPES: tuple[str, ...] = (
    "note",
    "spec",
    "research",
    "plan",
    "reference",
    "other",
)

DOC_STATUSES: tuple[str, ...] = ("draft", "published")

DOC_FORMATS: tuple[str, ...] = ("tiptap_json",)


def doc_type_check_sql(column: str = "doc_type") -> str:
    return _check_sql(column, DOC_TYPES)


def doc_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, DOC_STATUSES)


def doc_format_check_sql(column: str = "editor_format") -> str:
    return _check_sql(column, DOC_FORMATS)


# --- Phase 7A: Approval engine ------------------------------------------------
# ApprovalRequest lifecycle + binding enums. See docs/dev/phase-7a-approvals.md.
APPROVAL_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "applying",
    "applied",
    "rejected",
    "expired",
    "invalidated",
    "failed",
)

# Phase 7A was local-only; Phase 7B adds the MCP origin. The column still exists
# for forward compatibility (7C external HTTP).
APPROVAL_ORIGINS: tuple[str, ...] = ("local", "mcp")

APPROVAL_RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")

# The narrow, versioned action allowlist surfaced to the DB CHECK. The field-level
# policy lives in app/policy/allowlist.py and MUST stay in sync with this tuple
# (app/policy/allowlist.py asserts equality at import time).
APPROVAL_ACTION_TYPES: tuple[str, ...] = (
    "task.create",
    "task.update",
    "decision.create",
)

# Entity kinds an approval may target.
APPROVAL_TARGET_ENTITY_TYPES: tuple[str, ...] = ("task", "decision")


def approval_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, APPROVAL_STATUSES)


def approval_origin_check_sql(column: str = "origin") -> str:
    return _check_sql(column, APPROVAL_ORIGINS)


def approval_risk_level_check_sql(column: str = "risk_level") -> str:
    return _check_sql(column, APPROVAL_RISK_LEVELS)


def approval_action_type_check_sql(column: str = "action_type") -> str:
    return _check_sql(column, APPROVAL_ACTION_TYPES)


def approval_target_entity_type_check_sql(
    column: str = "target_entity_type",
) -> str:
    return _nullable_check_sql(column, APPROVAL_TARGET_ENTITY_TYPES)
