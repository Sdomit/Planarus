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
