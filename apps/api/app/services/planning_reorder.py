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
) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError("reorder ids must not contain duplicates")
    if set(ids) != set(rows.keys()):
        raise ValueError(
            f"reorder ids must match the project's {entity_type} rows exactly"
        )

    now = now_utc()
    for index, entity_id in enumerate(ids):
        row = rows[entity_id]
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
