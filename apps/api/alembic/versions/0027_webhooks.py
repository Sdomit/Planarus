"""Webhook subscriptions + delivery log (Phase 17.3, D38)

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-19

Additive only — two new tables for outbound webhooks:

* ``webhook_subscription`` — target URL + Fernet-encrypted HMAC signing secret
  (``secret_enc``) + JSON kind/project filters + auto-disable bookkeeping.
* ``webhook_delivery`` — one row per delivery attempt: the exact signed JSON
  envelope (kept verbatim for redeliver) plus status/code.

No existing table is touched. Downgrade drops both tables (and their indexes).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscription",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("target_url", sa.String(), nullable=False),
        sa.Column("secret_enc", sa.String(), nullable=False),
        sa.Column("event_kinds_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("project_ids_json", sa.String(), nullable=False, server_default="[]"),
        sa.Column("format", sa.String(), nullable=False, server_default="json"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("disabled_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspace.id"], name="fk_webhook_subscription_workspace"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_subscription_workspace_id", "webhook_subscription", ["workspace_id"]
    )

    op.create_table(
        "webhook_delivery",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscription_id", sa.String(), nullable=False),
        sa.Column("event_kind", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("request_body", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("delivered_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["subscription_id"],
            ["webhook_subscription.id"],
            name="fk_webhook_delivery_subscription",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_webhook_delivery_subscription_id", "webhook_delivery", ["subscription_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_webhook_delivery_subscription_id", table_name="webhook_delivery")
    op.drop_table("webhook_delivery")
    op.drop_index(
        "ix_webhook_subscription_workspace_id", table_name="webhook_subscription"
    )
    op.drop_table("webhook_subscription")
