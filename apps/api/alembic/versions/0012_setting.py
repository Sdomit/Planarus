"""Setting key/value table (Phase 9B — runtime settings & connection manager)

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-16

Additive only: one new `setting` table (key PK, JSON-encoded scalar value). No
existing table, CHECK, or index changes. Env-only deployments have zero rows and
behave exactly as before.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "setting",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("setting")
