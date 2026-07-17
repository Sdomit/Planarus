"""Custom statuses / board columns (Phase 15.5)

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-17

Adds the `status_option` table (per-project custom statuses per entity kind) and
drops the task `status` CHECK so a task may take a custom status. Validation
moves to the service layer (built-ins ∪ the project's custom keys). Additive for
data: existing task rows keep their canonical statuses.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshot of TASK_STATUSES for the downgrade CHECK re-creation.
_TASK_STATUSES = (
    "'backlog', 'ready', 'in_progress', 'waiting', "
    "'needs_review', 'blocked', 'done', 'canceled'"
)
_ENTITY_TYPES = "'task'"


def upgrade() -> None:
    op.create_table(
        "status_option",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"entity_type IN ({_ENTITY_TYPES})", name="ck_status_option_entity_type"
        ),
        sa.UniqueConstraint(
            "project_id", "entity_type", "key", name="uq_status_option_key"
        ),
    )
    op.create_index("ix_status_option_project_id", "status_option", ["project_id"])
    op.create_index(
        "ix_status_option_project_entity",
        "status_option",
        ["project_id", "entity_type", "sort_order"],
    )

    # Drop the task.status CHECK so custom statuses are accepted (service-layer
    # validation replaces it). Batch mode = SQLite copy-and-move.
    with op.batch_alter_table("task") as batch:
        batch.drop_constraint("ck_task_status", type_="check")


def downgrade() -> None:
    with op.batch_alter_table("task") as batch:
        batch.create_check_constraint(
            "ck_task_status", f"status IN ({_TASK_STATUSES})"
        )
    op.drop_index("ix_status_option_project_entity", table_name="status_option")
    op.drop_index("ix_status_option_project_id", table_name="status_option")
    op.drop_table("status_option")