"""ApiClient table + 'api' approval origin (Phase 7C1)

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-21

Additive:

1. Create the ``apiclient`` table (external API credentials; only an Argon2id
   verifier is stored — never a raw key).
2. Widen the ApprovalRequest origin CHECK from ('local','mcp') to
   ('local','mcp','api') so external-HTTP proposals are permitted.

SQLite-safe: the CHECK change uses Alembic batch (table recreate). The active-only
partial unique idempotency index is dropped before the batch and recreated after,
so its ``sqlite_where`` predicate is preserved exactly (it cannot be relied upon to
survive a batch reflect/recreate). CHECK value lists are frozen snapshots — do not
import runtime constants into a migration.

Downgrade refuses to delete data: it raises a clear error if any api-origin
ApprovalRequest rows or any ApiClient rows still exist, rather than silently
dropping them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# "failed" counts as active (apply() can retry it) — must match the model + 0006.
_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"


def upgrade() -> None:
    op.create_table(
        "apiclient",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(),
            sa.ForeignKey("workspace.id"),
            nullable=False,
        ),
        sa.Column("key_id", sa.String(), nullable=False),
        sa.Column("secret_hash", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("can_read", sa.Boolean(), nullable=False),
        sa.Column("can_propose", sa.Boolean(), nullable=False),
        sa.Column("project_ids_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("last_used_at", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.String(), nullable=True),
        sa.CheckConstraint(
            "can_read = 1 OR can_propose = 1",
            name="ck_apiclient_at_least_one_perm",
        ),
    )
    op.create_index("ix_apiclient_key_id", "apiclient", ["key_id"], unique=True)
    op.create_index("ix_apiclient_workspace_id", "apiclient", ["workspace_id"])

    # Widen the origin CHECK. Drop the partial unique index first so the batch
    # table-recreate does not have to reflect/reproduce its sqlite_where predicate.
    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")
    with op.batch_alter_table("approvalrequest") as batch_op:
        batch_op.drop_constraint("ck_approval_origin", type_="check")
        batch_op.create_check_constraint(
            "ck_approval_origin", "origin IN ('local', 'mcp', 'api')"
        )
    op.create_index(
        "uq_approval_active_idem",
        "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Refuse to delete data: api-origin approvals would violate the narrowed CHECK,
    # and ApiClient rows would be silently dropped with the table. Fail safely with
    # a clear error so a human resolves the data before downgrading.
    api_approvals = bind.execute(
        sa.text("SELECT COUNT(*) FROM approvalrequest WHERE origin = 'api'")
    ).scalar()
    if api_approvals:
        raise RuntimeError(
            f"refusing to downgrade 0007: {api_approvals} api-origin ApprovalRequest "
            "row(s) exist; resolve/migrate them before narrowing the origin CHECK"
        )
    api_clients = bind.execute(sa.text("SELECT COUNT(*) FROM apiclient")).scalar()
    if api_clients:
        raise RuntimeError(
            f"refusing to downgrade 0007: {api_clients} ApiClient row(s) exist; "
            "revoke and delete them deliberately before dropping the apiclient table"
        )

    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")
    with op.batch_alter_table("approvalrequest") as batch_op:
        batch_op.drop_constraint("ck_approval_origin", type_="check")
        batch_op.create_check_constraint(
            "ck_approval_origin", "origin IN ('local', 'mcp')"
        )
    op.create_index(
        "uq_approval_active_idem",
        "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
    )

    op.drop_index("ix_apiclient_workspace_id", table_name="apiclient")
    op.drop_index("ix_apiclient_key_id", table_name="apiclient")
    op.drop_table("apiclient")
