"""MCP origin + active-only idempotency uniqueness (Phase 7B)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-20

Additive, behavior-preserving for existing local proposals:

1. Widen the ApprovalRequest origin CHECK from ('local') to ('local','mcp').
2. Replace the *global* unique index on idempotency_key (0005) with an
   *active-only* partial unique index on (origin, actor_ref, idempotency_key),
   unique only while status is pending/approved/applying. A terminal proposal no
   longer blocks a later identical request.

SQLite-safe: the CHECK change uses Alembic batch (table recreate). CHECK value
lists are frozen snapshots — do not import runtime constants into a migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# "failed" counts as active: apply() can retry a failed proposal, so an identical
# re-proposal must dedupe to it rather than create a second applicable row.
_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"


def upgrade() -> None:
    # Drop the 0005 global unique index first so the table recreate below does not
    # reflect and re-create it.
    op.drop_index("uq_approval_idempotency_key", table_name="approvalrequest")

    # Widen the origin CHECK (SQLite requires a table rebuild → batch mode).
    with op.batch_alter_table("approvalrequest") as batch_op:
        batch_op.drop_constraint("ck_approval_origin", type_="check")
        batch_op.create_check_constraint(
            "ck_approval_origin", "origin IN ('local', 'mcp')"
        )

    # Active-only partial unique index. The predicate must be declared per
    # dialect: each backend only honors its own *_where kwarg and silently
    # ignores the other's, so omitting one would silently widen the index to a
    # full unique constraint on that backend (P10.0).
    op.create_index(
        "uq_approval_active_idem",
        "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
        postgresql_where=sa.text(_ACTIVE),
    )


def downgrade() -> None:
    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")

    with op.batch_alter_table("approvalrequest") as batch_op:
        batch_op.drop_constraint("ck_approval_origin", type_="check")
        batch_op.create_check_constraint("ck_approval_origin", "origin IN ('local')")

    op.create_index(
        "uq_approval_idempotency_key",
        "approvalrequest",
        ["idempotency_key"],
        unique=True,
    )
