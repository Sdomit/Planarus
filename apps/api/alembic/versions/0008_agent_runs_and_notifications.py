"""AgentRun, NotificationRule, EmailLog tables (Phase 9)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-10

Additive only: three new tables for the Phase 9 V1 expansion — manual agent-run
telemetry, per-project notification rules (email reminders), and the append-only
email send log. No existing table, CHECK, or index changes. CHECK value lists
are frozen snapshots — do not import runtime constants into a migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agentrun",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False
        ),
        sa.Column("agent_family", sa.String(), nullable=False),
        sa.Column("agent_name", sa.String(length=120), nullable=True),
        sa.Column("mode", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("summary", sa.String(), nullable=True),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("ended_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            "agent_family IN ('chatgpt', 'claude', 'codex', 'opencode', 'cursor', "
            "'custom', 'unspecified')",
            name="ck_agentrun_family",
        ),
        sa.CheckConstraint(
            "mode IS NULL OR mode IN ('plan', 'implement', 'review', 'debug', "
            "'summarize')",
            name="ck_agentrun_mode",
        ),
        sa.CheckConstraint(
            "status IN ('started', 'succeeded', 'failed', 'canceled')",
            name="ck_agentrun_status",
        ),
    )
    op.create_index("ix_agentrun_project_id", "agentrun", ["project_id"])
    op.create_index(
        "ix_agentrun_project_started", "agentrun", ["project_id", "started_at"]
    )

    op.create_table(
        "notificationrule",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column("trigger_type", sa.String(), nullable=False),
        # No server_default — matches the SQLModel definition exactly (the app
        # always supplies enabled); conftest builds schema from the models.
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("to_email", sa.String(length=254), nullable=False),
        sa.Column("threshold_hours", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            "channel IN ('in_app', 'desktop', 'email')",
            name="ck_notificationrule_channel",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('due_soon', 'daily_digest')",
            name="ck_notificationrule_trigger",
        ),
        sa.CheckConstraint("threshold_hours > 0", name="ck_notificationrule_threshold"),
    )
    op.create_index(
        "ix_notificationrule_project_id", "notificationrule", ["project_id"]
    )

    op.create_table(
        "emaillog",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False
        ),
        sa.Column(
            "rule_id", sa.String(), sa.ForeignKey("notificationrule.id"), nullable=True
        ),
        sa.Column("to_email", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("sent_at", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("status IN ('sent', 'failed')", name="ck_emaillog_status"),
    )
    op.create_index("ix_emaillog_project_id", "emaillog", ["project_id"])
    op.create_index("ix_emaillog_project_sent", "emaillog", ["project_id", "sent_at"])


def downgrade() -> None:
    op.drop_index("ix_emaillog_project_sent", table_name="emaillog")
    op.drop_index("ix_emaillog_project_id", table_name="emaillog")
    op.drop_table("emaillog")
    op.drop_index("ix_notificationrule_project_id", table_name="notificationrule")
    op.drop_table("notificationrule")
    op.drop_index("ix_agentrun_project_started", table_name="agentrun")
    op.drop_index("ix_agentrun_project_id", table_name="agentrun")
    op.drop_table("agentrun")
