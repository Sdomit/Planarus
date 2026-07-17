"""Add parent_task_id to task (Phase 15.8 — sub-tasks, one level)

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-16

Additive only: a nullable self-referential `parent_task_id` on `task` plus its
index. A task with a parent is a sub-task; nesting is capped at one level in the
service layer. Existing rows are all top-level (NULL parent).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode (copy-and-move) so SQLite can add the self-referential FK.
    with op.batch_alter_table("task") as batch:
        batch.add_column(sa.Column("parent_task_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_task_parent_task_id", "task", ["parent_task_id"], ["id"]
        )
    op.create_index("ix_task_parent_task_id", "task", ["parent_task_id"])


def downgrade() -> None:
    op.drop_index("ix_task_parent_task_id", table_name="task")
    with op.batch_alter_table("task") as batch:
        batch.drop_constraint("fk_task_parent_task_id", type_="foreignkey")
        batch.drop_column("parent_task_id")
