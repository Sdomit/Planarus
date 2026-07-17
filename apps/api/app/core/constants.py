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
    "canvas",  # Phase 13: an Excalidraw whiteboard is a Doc
)

DOC_STATUSES: tuple[str, ...] = ("draft", "published")

# tiptap_json = rich text (Tiptap/ProseMirror); excalidraw = canvas scene JSON.
# Widening this requires a paired migration rewriting ck_doc_format (0013 for
# 'excalidraw').
DOC_FORMATS: tuple[str, ...] = ("tiptap_json", "excalidraw")


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

# Phase 7A was local-only; Phase 7B adds the MCP origin; Phase 7C1 adds the
# external HTTP API origin. Widening this tuple requires a paired migration that
# rewrites the frozen ``ck_approval_origin`` CHECK (migration 0007 for 'api').
APPROVAL_ORIGINS: tuple[str, ...] = ("local", "mcp", "api")

APPROVAL_RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")

# The narrow, versioned action allowlist surfaced to the DB CHECK. The field-level
# policy lives in app/policy/allowlist.py and MUST stay in sync with this tuple
# (app/policy/allowlist.py asserts equality at import time). Widening this tuple
# requires a paired migration that rewrites ``ck_approval_action_type``
# (migration 0016 for 'doc.update').
APPROVAL_ACTION_TYPES: tuple[str, ...] = (
    "task.create",
    "task.update",
    "decision.create",
    "doc.update",  # Phase 13c: AI-proposed canvas/doc edits (content_json)
)

# Entity kinds an approval may target. Widening requires a paired migration that
# rewrites ``ck_approval_target_entity_type`` (migration 0016 for 'doc').
APPROVAL_TARGET_ENTITY_TYPES: tuple[str, ...] = ("task", "decision", "doc")


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


# --- Phase 9: agent runs + notifications ---------------------------------------
# AgentRun — manual, local-human-entered execution telemetry. `agent_family` and
# `mode` reuse the canonical lists from docs/plan/03-data-model.md.
AGENT_FAMILIES: tuple[str, ...] = (
    "chatgpt",
    "claude",
    "codex",
    "opencode",
    "cursor",
    "custom",
    "unspecified",
)

AGENT_RUN_MODES: tuple[str, ...] = (
    "plan",
    "implement",
    "review",
    "debug",
    "summarize",
)

AGENT_RUN_STATUSES: tuple[str, ...] = ("started", "succeeded", "failed", "canceled")


def agent_family_check_sql(column: str = "agent_family") -> str:
    return _check_sql(column, AGENT_FAMILIES)


def agent_run_mode_check_sql(column: str = "mode") -> str:
    return _nullable_check_sql(column, AGENT_RUN_MODES)


def agent_run_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, AGENT_RUN_STATUSES)


# NotificationRule / EmailLog. Only the email channel drives sends today; the
# in-app feed and desktop notifications are always-on client concerns.
NOTIFICATION_CHANNELS: tuple[str, ...] = ("in_app", "desktop", "email")

NOTIFICATION_TRIGGERS: tuple[str, ...] = ("due_soon", "daily_digest")

EMAIL_LOG_STATUSES: tuple[str, ...] = ("sent", "failed")


def notification_channel_check_sql(column: str = "channel") -> str:
    return _check_sql(column, NOTIFICATION_CHANNELS)


def notification_trigger_check_sql(column: str = "trigger_type") -> str:
    return _check_sql(column, NOTIFICATION_TRIGGERS)


def email_log_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, EMAIL_LOG_STATUSES)


# --- Phase 4b: Milestone, Comment, Link (completing the MVP data model) --------
MILESTONE_STATUSES: tuple[str, ...] = (
    "planned",
    "active",
    "achieved",
    "missed",
    "canceled",
)


def milestone_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, MILESTONE_STATUSES)


# Comment/Link are polymorphic: they attach to any project-scoped entity via
# (entity_type, entity_id). This is the target-kind allowlist (03-data-model.md).
REF_ENTITY_TYPES: tuple[str, ...] = (
    "project",
    "phase",
    "stage",
    "task",
    "decision",
    "risk",
    "blocker",
    "milestone",
    "doc",
    "calendar_event",
)


# --- Phase 15.12: CalendarEvent (calendar surface) ----------------------------
# A first-class dated event. Statuses mirror the common calendar vocabulary
# (Google/CalDAV): confirmed / tentative / cancelled.
CALENDAR_EVENT_STATUSES: tuple[str, ...] = ("confirmed", "tentative", "cancelled")


def calendar_event_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, CALENDAR_EVENT_STATUSES)


# Recurrence for calendar events. Deliberately small: none / daily / weekly /
# monthly + an optional inclusive until-date. Full RRULE (intervals, BYDAY,
# per-occurrence exceptions) is out of scope — see calendar_service._occurrences.
CALENDAR_RECURRENCE_TYPES: tuple[str, ...] = ("none", "daily", "weekly", "monthly")


# --- Phase 15.12b: external calendar sync (Google / Microsoft) -----------------
CALENDAR_SYNC_PROVIDERS: tuple[str, ...] = ("google", "microsoft")
# connected: healthy; error: last sync/refresh failed; revoked: token rejected.
CALENDAR_CONNECTION_STATUSES: tuple[str, ...] = ("connected", "error", "revoked")


def calendar_connection_status_check_sql(column: str = "status") -> str:
    return _check_sql(column, CALENDAR_CONNECTION_STATUSES)


def calendar_connection_provider_check_sql(column: str = "provider") -> str:
    return _check_sql(column, CALENDAR_SYNC_PROVIDERS)

# Who authored a comment. Local-app comments are "human"; the field exists so an
# approval-gated agent comment can be attributed without a schema change later.
COMMENT_AUTHOR_TYPES: tuple[str, ...] = ("human", "agent", "system")


def comment_entity_type_check_sql(column: str = "entity_type") -> str:
    return _check_sql(column, REF_ENTITY_TYPES)


def comment_author_type_check_sql(column: str = "author_type") -> str:
    return _check_sql(column, COMMENT_AUTHOR_TYPES)


def link_entity_type_check_sql(column: str = "entity_type") -> str:
    return _check_sql(column, REF_ENTITY_TYPES)


# --- Phase 10.1: identity + workspace membership (hosted mode) -----------------
# Workspace-scoped RBAC roles (D19). Capability is nested: owner ⊃ editor ⊃
# viewer. owner manages membership + (from P10.2) approves/applies; editor
# creates/edits domain state + proposes; viewer is read-only.
WORKSPACE_ROLES: tuple[str, ...] = ("owner", "editor", "viewer")

# Authentication identity providers. "dev" is a password-less, doubly-gated local
# provider for bootstrap + tests (never usable unless BOTH AGENTBOARD_AUTH_ENABLED
# and AGENTBOARD_AUTH_DEV_LOGIN are on); real OAuth providers wire in at P10.1b.
AUTH_PROVIDERS: tuple[str, ...] = ("dev", "google", "github")


def workspace_role_check_sql(column: str = "role") -> str:
    return _check_sql(column, WORKSPACE_ROLES)


def auth_provider_check_sql(column: str = "provider") -> str:
    return _check_sql(column, AUTH_PROVIDERS)
