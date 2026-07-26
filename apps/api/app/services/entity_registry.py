"""Single source of truth for the referenceable entity types (#94).

``REF_ENTITY_TYPES`` is the contract advertised by the comment/link/note schemas,
the DB CHECK constraints and OpenAPI. Before this module, two hand-maintained
maps restated that list and both had drifted from it:

- ``entity_ref._REF_MODELS`` omitted ``calendar_event``, so a POST carrying that
  (schema-valid, CHECK-valid) type raised ``KeyError`` and surfaced as a 404
  whose entire detail was the type name.
- ``timeline_service._RESOLVERS`` omitted ``milestone`` and ``calendar_event``,
  both of which are audited, so their timeline rows rendered without titles.

Both maps are now derived from ``ENTITY_MODELS`` here, and the import-time assert
below fails the process if it ever drifts from ``REF_ENTITY_TYPES`` again. This
mirrors the pattern ``policy/allowlist.py`` already uses for its action list.
"""
from __future__ import annotations

from typing import Type

from sqlmodel import SQLModel

from app.core.constants import REF_ENTITY_TYPES
from app.models.blocker import Blocker
from app.models.calendar_event import CalendarEvent
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task

# entity_type -> (model, attribute holding the human-readable label).
# Every model here except Project carries a `project_id` column; "project" is
# scope-checked against the project id itself rather than a column.
ENTITY_MODELS: dict[str, tuple[Type[SQLModel], str]] = {
    "project": (Project, "title"),
    "phase": (Phase, "title"),
    "stage": (Stage, "title"),
    "task": (Task, "title"),
    "decision": (Decision, "title"),
    "risk": (Risk, "title"),
    "blocker": (Blocker, "title"),
    "milestone": (Milestone, "title"),
    "doc": (Doc, "title"),
    "calendar_event": (CalendarEvent, "title"),
}

# Fail fast if the advertised type list and the model map ever drift apart.
assert set(ENTITY_MODELS) == set(
    REF_ENTITY_TYPES
), "ENTITY_MODELS must match REF_ENTITY_TYPES"

# Every label attribute must actually exist on its model, or a timeline row would
# resolve to an AttributeError at render time instead of at import.
for _entity_type, (_model, _attr) in ENTITY_MODELS.items():
    assert hasattr(
        _model, _attr
    ), f"{_model.__name__} has no attribute '{_attr}' (entity_type '{_entity_type}')"


def model_for(entity_type: str) -> Type[SQLModel]:
    """Return the SQLModel class backing ``entity_type``."""
    return ENTITY_MODELS[entity_type][0]


def label_attr_for(entity_type: str) -> str:
    """Return the attribute name holding ``entity_type``'s display label."""
    return ENTITY_MODELS[entity_type][1]
