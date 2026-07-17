"""Todo table — project-scoped, self-nesting sidebar todos

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-17

Additive only: one new ``todo`` table. Self-referential ``parent_id`` gives
arbitrary nesting depth (sub, sub-sub, …). No existing table/CHECK/index changes.

Renumbered from 0023 → 0024 at merge time: main already had a 0023
(custom_status_milestone_decision) off 0022, so this chains onto it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "todo",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("parent_id", sa.String(), sa.ForeignKey("todo.id"), nullable=True),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_todo_project_sort", "todo", ["project_id", "sort_order"])
    op.create_index("ix_todo_parent_id", "todo", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_todo_parent_id", table_name="todo")
    op.drop_index("ix_todo_project_sort", table_name="todo")
    op.drop_table("todo")
