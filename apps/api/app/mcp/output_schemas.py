"""JSON Schema output declarations for MCP tools (#184).

Each schema describes ``ToolResult.metadata`` — the safe-scalar dict returned
alongside the wrapped, untrusted text block (see ``serializers.ToolResult``).
Declaring the shape lets a client validate and destructure metadata instead of
parsing prose. The wrapped *text* is untrusted project content and is
deliberately never described here — only the scalar metadata contract.

Two helpers assemble the envelopes ``serializers.build_result`` and
``read_tools._page_metadata`` attach, so each tool's own schema lists only what
it actually adds:

- ``_ENVELOPE``: ``field_truncated`` and ``approximate_token_estimate`` are
  attached by every ``build_result`` call, unconditionally — required.
  ``secret_findings`` / ``injection_flags`` are attached only when something
  was actually found — declared, but NOT required.
- ``_PAGE``: attached by every ``list_*`` tool via ``_page_metadata``.

``get_approval_status`` uses ``status_only_result`` and the propose tools build
their own dict directly (``_proposal_result``) — neither goes through
``build_result``, so neither gets the envelope.
"""
from __future__ import annotations

_ENVELOPE_PROPERTIES = {
    "field_truncated": {"type": "boolean"},
    "approximate_token_estimate": {"type": "integer"},
    "secret_findings": {"type": "array", "items": {"type": "string"}},
    "injection_flags": {"type": "array", "items": {"type": "string"}},
}
_ENVELOPE_REQUIRED = ("field_truncated", "approximate_token_estimate")

_PAGE_PROPERTIES = {
    "limit": {"type": "integer"},
    "offset": {"type": "integer"},
    "row_truncated": {"type": "boolean"},
    "next_offset": {"type": ["integer", "null"]},
}
_PAGE_REQUIRED = ("limit", "offset", "row_truncated", "next_offset")


def _schema(
    properties: dict,
    required: tuple[str, ...],
    *,
    envelope: bool = True,
    paged: bool = False,
) -> dict:
    props = dict(properties)
    req = list(required)
    if paged:
        props.update(_PAGE_PROPERTIES)
        req += _PAGE_REQUIRED
    if envelope:
        props.update(_ENVELOPE_PROPERTIES)
        req += _ENVELOPE_REQUIRED
    return {"type": "object", "properties": props, "required": sorted(set(req))}


# --- read tools ---------------------------------------------------------------

LIST_PROJECTS = _schema(
    {
        "count": {"type": "integer"},
        "project_ids": {"type": "array", "items": {"type": "string"}},
        "statuses": {"type": "object"},
    },
    ("count", "project_ids", "statuses"),
)

LIST_STATUS_OPTIONS = _schema(
    {
        "project_id": {"type": "string"},
        "entity_type": {"type": "string", "enum": ["task", "decision", "phase", "milestone", "risk"]},
        "default_status": {"type": "string"},
        "count": {"type": "integer"},
        "status_keys": {"type": "array", "items": {"type": "string"}},
    },
    ("project_id", "entity_type", "default_status", "count", "status_keys"),
    envelope=False,
    paged=True,
)


GET_PROJECT_SUMMARY = _schema(
    {
        "project_id": {"type": "string"},
        "status": {"type": "string"},
        "task_count": {"type": "integer"},
        "open_risk_count": {"type": "integer"},
        "decision_count": {"type": "integer"},
        "doc_count": {"type": "integer"},
        "phase_count": {"type": "integer"},
    },
    (
        "project_id", "status", "task_count", "open_risk_count",
        "decision_count", "doc_count", "phase_count",
    ),
)

GET_ACTIVE_WORK = _schema(
    {
        "project_id": {"type": "string"},
        "active_phase_id": {"type": ["string", "null"]},
        "phase_count": {"type": "integer"},
        "active_task_count": {"type": "integer"},
        "active_task_truncated": {"type": "boolean"},
        "phase_decision_count": {"type": "integer"},
        "phase_open_risk_count": {"type": "integer"},
        "open_blocker_count": {"type": "integer"},
        "open_blocker_truncated": {"type": "boolean"},
        "phase_ids": {"type": "array", "items": {"type": "string"}},
    },
    (
        "project_id", "active_phase_id", "phase_count", "active_task_count",
        "active_task_truncated", "phase_decision_count", "phase_open_risk_count",
        "open_blocker_count", "open_blocker_truncated", "phase_ids",
    ),
)

LIST_TASKS = _schema(
    {
        "project_id": {"type": "string"},
        "count": {"type": "integer"},
        "task_ids": {"type": "array", "items": {"type": "string"}},
        "statuses": {"type": "array", "items": {"type": "string"}},
    },
    ("project_id", "count", "task_ids", "statuses"),
    paged=True,
)

LIST_DECISIONS = _schema(
    {
        "project_id": {"type": "string"},
        "phase_id": {"type": ["string", "null"]},
        "count": {"type": "integer"},
        "decision_ids": {"type": "array", "items": {"type": "string"}},
        "statuses": {"type": "array", "items": {"type": "string"}},
    },
    ("project_id", "phase_id", "count", "decision_ids", "statuses"),
    paged=True,
)

LIST_RISKS = _schema(
    {
        "project_id": {"type": "string"},
        "phase_id": {"type": ["string", "null"]},
        "count": {"type": "integer"},
        "risk_ids": {"type": "array", "items": {"type": "string"}},
        "severities": {"type": "array", "items": {"type": "string"}},
        "statuses": {"type": "array", "items": {"type": "string"}},
    },
    ("project_id", "phase_id", "count", "risk_ids", "severities", "statuses"),
    paged=True,
)

LIST_PHASES = _schema(
    {"project_id": {"type": "string"}, "count": {"type": "integer"},
     "phase_ids": {"type": "array", "items": {"type": "string"}},
     "statuses": {"type": "array", "items": {"type": "string"}}},
    ("project_id", "count", "phase_ids", "statuses"), paged=True,
)

LIST_MILESTONES = _schema(
    {"project_id": {"type": "string"}, "phase_id": {"type": ["string", "null"]},
     "count": {"type": "integer"},
     "milestone_ids": {"type": "array", "items": {"type": "string"}},
     "statuses": {"type": "array", "items": {"type": "string"}}},
    ("project_id", "phase_id", "count", "milestone_ids", "statuses"), paged=True,
)

LIST_COMMENTS = _schema(
    {"project_id": {"type": "string"}, "count": {"type": "integer"},
     "comment_ids": {"type": "array", "items": {"type": "string"}}},
    ("project_id", "count", "comment_ids"), paged=True,
)

LIST_LINKS = _schema(
    {"project_id": {"type": "string"}, "count": {"type": "integer"},
     "link_ids": {"type": "array", "items": {"type": "string"}}},
    ("project_id", "count", "link_ids"), paged=True,
)

LIST_CONNECTIONS = _schema(
    {"project_id": {"type": "string"}, "count": {"type": "integer"},
     "connection_ids": {"type": "array", "items": {"type": "string"}},
     "source_entity_ids": {"type": "array", "items": {"type": "string"}},
     "target_entity_ids": {"type": "array", "items": {"type": "string"}}},
    ("project_id", "count", "connection_ids", "source_entity_ids", "target_entity_ids"), paged=True,
)

LIST_DOCS = _schema(
    {
        "project_id": {"type": "string"},
        "count": {"type": "integer"},
        "doc_ids": {"type": "array", "items": {"type": "string"}},
        "doc_types": {"type": "array", "items": {"type": "string"}},
    },
    ("project_id", "count", "doc_ids", "doc_types"),
    paged=True,
)

GET_DOC_EXCERPT = _schema(
    {
        "doc_id": {"type": "string"},
        "project_id": {"type": "string"},
        "doc_type": {"type": "string"},
        "status": {"type": "string"},
        "version": {"type": "integer"},
        "max_chars": {"type": "integer"},
        "offset": {"type": "integer"},
        "full_length": {"type": "integer"},
        "excerpt_length": {"type": "integer"},
        "next_offset": {"type": ["integer", "null"]},
    },
    (
        "doc_id", "project_id", "doc_type", "status", "version", "max_chars",
        "offset", "full_length", "excerpt_length", "next_offset",
    ),
)

GET_ITEM = _schema(
    {
        "kind": {"type": "string", "enum": ["task", "decision", "risk", "doc", "phase", "milestone", "comment", "link"]},
        "item_id": {"type": "string"},
        "project_id": {"type": "string"},
        "max_chars": {"type": "integer"},
    },
    ("kind", "item_id", "project_id", "max_chars"),
)

GET_APPROVAL_STATUS = _schema(
    {
        "approval_id": {"type": "string"},
        "status": {"type": "string"},
        "action_type": {"type": "string"},
        "target_entity_type": {"type": ["string", "null"]},
        "target_entity_id": {"type": ["string", "null"]},
        "applied_entity_type": {"type": ["string", "null"]},
        "applied_entity_id": {"type": ["string", "null"]},
        "origin": {"type": "string"},
        "expires_at": {"type": "string"},
        "applied_at": {"type": ["string", "null"]},
    },
    (
        "approval_id", "status", "action_type", "target_entity_type",
        "target_entity_id", "applied_entity_type", "applied_entity_id",
        "origin", "expires_at", "applied_at",
    ),
    envelope=False,
)

# --- propose tools --------------------------------------------------------------
# Proposal tools return the identical shape (_proposal_result in
# tools/propose.py) — one shared schema rather than a copy per action.

_PROPOSAL_RESULT = _schema(
    {
        "approval_id": {"type": "string"},
        "status": {"type": "string"},
        "action_type": {"type": "string"},
        "expires_at": {"type": "string"},
        "review_hint": {"type": "string"},
    },
    ("approval_id", "status", "action_type", "expires_at", "review_hint"),
    envelope=False,
)

CREATE_TASK_PROPOSAL = _PROPOSAL_RESULT
UPDATE_TASK_PROPOSAL = _PROPOSAL_RESULT
CREATE_DECISION_PROPOSAL = _PROPOSAL_RESULT
UPDATE_CANVAS_PROPOSAL = _PROPOSAL_RESULT
CREATE_CONNECTION_PROPOSAL = _PROPOSAL_RESULT
CREATE_PHASE_PROPOSAL = _PROPOSAL_RESULT
UPDATE_PHASE_PROPOSAL = _PROPOSAL_RESULT
CREATE_MILESTONE_PROPOSAL = _PROPOSAL_RESULT
UPDATE_MILESTONE_PROPOSAL = _PROPOSAL_RESULT
CREATE_RISK_PROPOSAL = _PROPOSAL_RESULT
UPDATE_RISK_PROPOSAL = _PROPOSAL_RESULT
UPDATE_DECISION_PROPOSAL = _PROPOSAL_RESULT
CREATE_COMMENT_PROPOSAL = _PROPOSAL_RESULT
CREATE_LINK_PROPOSAL = _PROPOSAL_RESULT
