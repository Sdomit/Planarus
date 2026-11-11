"""Allow approval-gated MCP URL link proposals.

Revision ID: 0039
Revises: 0038
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"
_OLD_ACTIONS = (
    "'task.create', 'task.update', 'decision.create', 'doc.update', 'connection.create', "
    "'phase.create', 'phase.update', 'milestone.create', 'milestone.update', "
    "'risk.create', 'risk.update', 'decision.update', 'comment.create'"
)
_OLD_TARGETS = "'task', 'decision', 'doc', 'entity_connection', 'phase', 'milestone', 'risk', 'comment'"


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
    _swap(_OLD_ACTIONS + ", 'link.create'", _OLD_TARGETS + ", 'link'")


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM approvalrequest WHERE action_type = 'link.create'"
    )).scalar()
    if count:
        raise RuntimeError("cannot remove link approval action while link proposals exist")
    _swap(_OLD_ACTIONS, _OLD_TARGETS)
