"""Canonical domain constants shared across schemas, models, and validation.

Migrations intentionally do NOT import from here — a migration is a frozen
snapshot of the schema at authoring time, so it hardcodes its own value list.
Keep the migration's CHECK list in sync with `PROJECT_STATUSES` by hand when a
new status is introduced (that change ships as a new migration revision).
"""

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
    """Return a SQL CHECK expression restricting `column` to PROJECT_STATUSES."""
    values = ", ".join(f"'{status}'" for status in PROJECT_STATUSES)
    return f"{column} IN ({values})"
