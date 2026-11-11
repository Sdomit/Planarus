"""Allow approval-gated MCP proposals for planning records and comments.

Revision ID: 0038
Revises: 0037
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"
_OLD_ACTIONS = "'task.create', 'task.update', 'decision.create', 'doc.update', 'connection.create'"
_NEW_ACTIONS = _OLD_ACTIONS + (
    ", 'phase.create', 'phase.update', 'milestone.create', 'milestone.update'"
    ", 'risk.create', 'risk.update', 'decision.update', 'comment.create'"
)
_OLD_TARGETS = "'task', 'decision', 'doc', 'entity_connection'"
_NEW_TARGETS = _OLD_TARGETS + ", 'phase', 'milestone', 'risk', 'comment'"


def _swap(actions: str, targets: str) -> None:
    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")
    with op.batch_alter_table("approvalrequest") as batch:
        batch.drop_constraint("ck_approval_action_type", type_="check")
        batch.create_check_constraint("ck_approval_action_type", f"action_type IN ({actions})")
        batch.drop_constraint("ck_approval_target_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_approval_target_entity_type",
            f"target_entity_type IS NULL OR target_entity_type IN ({targets})",
        )
    op.create_index(
        "uq_approval_active_idem", "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"], unique=True,
        sqlite_where=sa.text(_ACTIVE), postgresql_where=sa.text(_ACTIVE),
    )


def upgrade() -> None:
    _swap(_NEW_ACTIONS, _NEW_TARGETS)


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM approvalrequest WHERE action_type IN ("
        "'phase.create', 'phase.update', 'milestone.create', 'milestone.update', "
        "'risk.create', 'risk.update', 'decision.update', 'comment.create')"
    )).scalar()
    if count:
        raise RuntimeError("cannot remove planning approval actions while their proposals exist")
    _swap(_OLD_ACTIONS, _OLD_TARGETS)
