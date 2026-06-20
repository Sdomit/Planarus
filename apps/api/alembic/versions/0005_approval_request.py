"""ApprovalRequest: Phase 7A approval engine

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-20

Additive migration — creates the `approvalrequest` table. No ALTER TABLE on
existing tables. CHECK values are frozen snapshots; keep in sync with
app/core/constants.py (a new value ships as a new revision).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen CHECK value lists (do not import from constants — migration is a snapshot).
_STATUSES = (
    "'pending', 'approved', 'applying', 'applied', 'rejected', 'expired', "
    "'invalidated', 'failed'"
)
_ORIGINS = "'local'"
_RISK_LEVELS = "'low', 'medium', 'high'"
_ACTION_TYPES = "'task.create', 'task.update', 'decision.create'"
_TARGET_TYPES = "'task', 'decision'"


def upgrade() -> None:
    op.create_table(
        "approvalrequest",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(),
            sa.ForeignKey("workspace.id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("project.id"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(), nullable=False, server_default="local"),
        sa.Column("actor_ref", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("target_entity_type", sa.String(), nullable=True),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("proposed_patch_json", sa.Text(), nullable=False),
        sa.Column("patch_checksum", sa.String(), nullable=False),
        sa.Column("base_target_fingerprint", sa.String(), nullable=True),
        sa.Column("base_versions_json", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False, server_default="low"),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("decided_at", sa.String(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("applied_at", sa.String(), nullable=True),
        sa.Column(
            "applied_audit_event_id",
            sa.String(),
            sa.ForeignKey("auditevent.id"),
            nullable=True,
        ),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_approval_status"),
        sa.CheckConstraint(f"origin IN ({_ORIGINS})", name="ck_approval_origin"),
        sa.CheckConstraint(
            f"risk_level IN ({_RISK_LEVELS})", name="ck_approval_risk_level"
        ),
        sa.CheckConstraint(
            f"action_type IN ({_ACTION_TYPES})", name="ck_approval_action_type"
        ),
        sa.CheckConstraint(
            f"target_entity_type IS NULL OR target_entity_type IN ({_TARGET_TYPES})",
            name="ck_approval_target_entity_type",
        ),
    )
    op.create_index(
        "ix_approval_workspace_status", "approvalrequest", ["workspace_id", "status"]
    )
    op.create_index(
        "ix_approval_project_status", "approvalrequest", ["project_id", "status"]
    )
    op.create_index("ix_approval_status", "approvalrequest", ["status"])
    op.create_index("ix_approval_expires_at", "approvalrequest", ["expires_at"])
    op.create_index("ix_approval_origin", "approvalrequest", ["origin"])
    op.create_index("ix_approval_workspace_id", "approvalrequest", ["workspace_id"])
    op.create_index("ix_approval_project_id", "approvalrequest", ["project_id"])
    op.create_index(
        "ix_approval_applied_audit_event_id",
        "approvalrequest",
        ["applied_audit_event_id"],
    )
    op.create_index(
        "uq_approval_idempotency_key",
        "approvalrequest",
        ["idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_approval_idempotency_key", table_name="approvalrequest")
    op.drop_index("ix_approval_applied_audit_event_id", table_name="approvalrequest")
    op.drop_index("ix_approval_project_id", table_name="approvalrequest")
    op.drop_index("ix_approval_workspace_id", table_name="approvalrequest")
    op.drop_index("ix_approval_origin", table_name="approvalrequest")
    op.drop_index("ix_approval_expires_at", table_name="approvalrequest")
    op.drop_index("ix_approval_status", table_name="approvalrequest")
    op.drop_index("ix_approval_project_status", table_name="approvalrequest")
    op.drop_index("ix_approval_workspace_status", table_name="approvalrequest")
    op.drop_table("approvalrequest")
