"""ContextFile table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contextfile",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("generated_at", sa.String(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_manual_edit_at", sa.String(), nullable=True),
        sa.Column("token_estimate", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "project_id", "relative_path", name="uq_contextfile_project_path"
        ),
    )
    op.create_index("ix_contextfile_project_id", "contextfile", ["project_id"])
    op.create_index("ix_contextfile_kind", "contextfile", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_contextfile_kind", table_name="contextfile")
    op.drop_index("ix_contextfile_project_id", table_name="contextfile")
    op.drop_table("contextfile")
