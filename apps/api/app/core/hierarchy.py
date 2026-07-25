"""Same-project parent validation for self-referencing entities (#116).

A self-referencing foreign key proves only that the parent id exists *somewhere*.
Docs accepted `parent_doc_id` straight from the payload, so a workspace editor
could parent a project-A document to a project-B one — and deleting the project-B
parent then reached into project A to clear the child's `parent_doc_id`, a write
across the tenant boundary inside the victim's transaction.

Docs are the first self-referencing model; phases, tasks and the entity-connection
spine are the same shape, so the check lives here rather than in `doc_service`.

Raises ``TypeError`` for every rejection, which the v1 endpoints already map to
422 — an invalid parent is an unprocessable payload, not a missing route. Callers
that want 404-on-missing can catch it and re-raise.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlmodel import Session

#: A parent chain longer than this is treated as a cycle. Real doc trees are a
#: handful deep; the bound also stops a pre-existing data cycle (see
#: ``doc_service.repair_parent_integrity``) from spinning the walk forever.
MAX_DEPTH = 64


def validate_parent(
    session: Session,
    model: type,
    *,
    parent_id: Optional[str],
    project_id: str,
    child_id: Optional[str] = None,
    parent_attr: str = "parent_id",
    label: str = "parent",
) -> Optional[str]:
    """Return ``parent_id`` if it may legally parent ``child_id``, else raise.

    ``child_id`` is None on create — there is no row yet, so self-parenting and
    cycles are impossible and only existence plus project match are checked.
    """
    if parent_id is None:
        return None
    if child_id is not None and parent_id == child_id:
        raise TypeError(f"{label} cannot be itself")

    parent: Any = session.get(model, parent_id)
    if parent is None:
        raise TypeError(f"{label} {parent_id!r} not found")
    if getattr(parent, "project_id", None) != project_id:
        # Deliberately the same message as "not found": a caller probing ids
        # across projects learns nothing about which ones exist.
        raise TypeError(f"{label} {parent_id!r} not found")

    if child_id is None:
        return parent_id

    # Walk up from the proposed parent. Meeting the child means the new edge
    # would close a loop; ``seen`` catches a loop that already exists upstream.
    seen = {child_id}
    node = parent
    for _ in range(MAX_DEPTH):
        node_id = getattr(node, "id", None)
        if node_id in seen:
            raise TypeError(f"{label} would create a cycle")
        seen.add(node_id)
        next_id = getattr(node, parent_attr, None)
        if next_id is None:
            return parent_id
        node = session.get(model, next_id)
        if node is None:
            return parent_id
    raise TypeError(f"{label} chain is deeper than {MAX_DEPTH}")
