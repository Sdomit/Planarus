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

from typing import Iterable, Mapping, Type

from sqlmodel import Session, SQLModel, select

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


def titles_for(
    session: Session,
    wanted: Mapping[str, Iterable[str]],
    *,
    project_id: str | None = None,
) -> dict[tuple[str, str], str]:
    """Batch-resolve display labels: ``{entity_type: ids} -> {(type, id): title}``.

    One query per entity type present, not one per row. Unknown types and missing
    ids are simply absent from the result, so a caller renders its own fallback
    rather than raising on a deleted target.

    ``project_id`` scopes the lookup. It is optional because the original callers
    pass ids they already resolved inside one project, which made the scoping
    implicit — correct, but only by construction, and a raw ``id IN (...)`` is a
    poor place to leave that kind of invariant unstated. Pass it wherever the ids
    came from user-supplied or document-derived data, so a title cannot be read
    across the tenant boundary even if the caller's own filtering regresses.

    ponytail: ``timeline_service`` runs the same loop over its own resolver map
    (ENTITY_MODELS plus four audit-only types). Give this a resolvers argument and
    fold that one in if a third caller ever wants it.
    """
    titles: dict[tuple[str, str], str] = {}
    for entity_type, ids in wanted.items():
        if entity_type not in ENTITY_MODELS:
            continue
        ids = list(ids)
        if not ids:
            continue
        model, attr = ENTITY_MODELS[entity_type]
        stmt = select(model).where(model.id.in_(ids))  # type: ignore[attr-defined]
        # "project" is the tenant root and carries no project_id column of its own.
        if project_id is not None and entity_type != "project":
            stmt = stmt.where(model.project_id == project_id)  # type: ignore[attr-defined]
        for row in session.exec(stmt).all():
            titles[(entity_type, row.id)] = str(getattr(row, attr))
    return titles


def model_for(entity_type: str) -> Type[SQLModel]:
    """Return the SQLModel class backing ``entity_type``."""
    return ENTITY_MODELS[entity_type][0]


def label_attr_for(entity_type: str) -> str:
    """Return the attribute name holding ``entity_type``'s display label."""
    return ENTITY_MODELS[entity_type][1]
