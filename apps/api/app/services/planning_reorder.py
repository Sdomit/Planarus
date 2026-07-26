"""Shared reorder plumbing for sort_order-bearing planning entities.

`apply_reorder` rewrites each row's `sort_order` to its index in `ids` inside a
single transaction, and emits one `reorder` audit event for the whole batch. The
`ids` list must match the project's rows of that kind exactly — this keeps the
resulting order total and deterministic (no gaps, no collisions).
"""
from typing import Any

from sqlmodel import Session

from app.core.utils import now_utc
from app.services.audit_service import create_audit_event


def apply_reorder(
    session: Session,
    *,
    project_id: str,
    entity_type: str,
    rows: dict[str, Any],
    ids: list[str],
) -> list[Any]:
    """Renumber `rows` into `ids` order and return them in that order.

    #103: two things this used to do that it no longer does.

    Rows already sitting at their target index are skipped, so a drag now writes
    only the rows it actually moved instead of every row of the type — dragging
    one card to an adjacent slot was ~200 UPDATEs on a 200-task board. Skipping
    them also leaves `updated_at` alone on rows that genuinely did not change,
    which is the honest value.

    Returning the ordered rows lets callers stop re-listing the whole table just
    to answer the request. That is exact, not an approximation: `sort_order`
    ends up as 0..n-1 with no duplicates, so every caller's
    `ORDER BY sort_order, ...` yields precisely this order and its tiebreaks
    can never fire.
    """
    if len(set(ids)) != len(ids):
        raise ValueError("reorder ids must not contain duplicates")
    if set(ids) != set(rows.keys()):
        raise ValueError(
            f"reorder ids must match the project's {entity_type} rows exactly"
        )

    now = now_utc()
    ordered = [rows[entity_id] for entity_id in ids]
    for index, row in enumerate(ordered):
        if row.sort_order == index:
            continue
        row.sort_order = index
        row.updated_at = now
        session.add(row)
    create_audit_event(
        session,
        event_type="reorder",
        actor_type="human",
        entity_type=entity_type,
        project_id=project_id,
    )
    session.commit()
    return ordered
