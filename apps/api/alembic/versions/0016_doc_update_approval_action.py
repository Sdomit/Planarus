"""Widen approval CHECKs for doc.update proposals (Phase 13c)

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-17

Additive: widen ``ck_approval_action_type`` to include ``'doc.update'`` and
``ck_approval_target_entity_type`` to include ``'doc'`` so AI-proposed canvas/doc
edits can be recorded as pending ApprovalRequests. No new column or table.

SQLite-safe: the CHECK changes use Alembic batch (table recreate). The active-only
partial unique idempotency index is dropped before the batch and recreated after,
so its ``sqlite_where`` predicate is preserved exactly (a batch reflect/recreate
cannot be relied on to reproduce it). CHECK value lists are frozen snapshots — do
not import runtime constants into a migration.

Downgrade refuses to delete data: it raises a clear error if any doc.update /
doc-target ApprovalRequest rows still exist, rather than silently violating the
narrowed CHECK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# "failed" counts as active (apply() can retry it) — must match the model + 0006/0007.
_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"

_ACTION_OLD = "action_type IN ('task.create', 'task.update', 'decision.create')"
_ACTION_NEW = (
    "action_type IN ('task.create', 'task.update', 'decision.create', 'doc.update')"
)
_TARGET_OLD = "target_entity_type IS NULL OR target_entity_type IN ('task', 'decision')"
_TARGET_NEW = (
    "target_entity_type IS NULL OR target_entity_type IN ('task', 'decision', 'doc')"
)


def _swap(action_sql: str, target_sql: str) -> None:
    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")
    with op.batch_alter_table("approvalrequest") as batch_op:
        batch_op.drop_constraint("ck_approval_action_type", type_="check")
        batch_op.create_check_constraint("ck_approval_action_type", action_sql)
        batch_op.drop_constraint("ck_approval_target_entity_type", type_="check")
        batch_op.create_check_constraint("ck_approval_target_entity_type", target_sql)
    op.create_index(
        "uq_approval_active_idem",
        "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"],
        unique=True,
        # Both dialects' *_where must be declared; each backend ignores the other's
        # kwarg, which would silently drop the partial predicate (P10.0).
        sqlite_where=sa.text(_ACTIVE),
        postgresql_where=sa.text(_ACTIVE),
    )


def upgrade() -> None:
    _swap(_ACTION_NEW, _TARGET_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM approvalrequest "
            "WHERE action_type = 'doc.update' OR target_entity_type = 'doc'"
        )
    ).scalar()
    if n:
        raise RuntimeError(
            f"refusing to downgrade 0016: {n} doc.update/doc-target approval row(s) "
            "exist; resolve them before narrowing the approval CHECKs"
        )
    _swap(_ACTION_OLD, _TARGET_OLD)
