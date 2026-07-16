"""SyncBaseline table (Phase 10.6b — sync apply + baseline persistence)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-16

Additive: one table storing the last-synced content manifest per project, so a
future three-way diff can distinguish a one-sided change from a conflict. Inert
until sync is actually run. Dialect-portable (P10.0 discipline).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "syncbaseline",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_syncbaseline_project_id", "syncbaseline", ["project_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_syncbaseline_project_id", table_name="syncbaseline")
    op.drop_table("syncbaseline")
