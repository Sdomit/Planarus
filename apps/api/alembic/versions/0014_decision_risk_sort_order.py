"""Add sort_order to decision + risk (Phase 15.3 — manual reordering)

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-16

Additive only: a nullable-with-default `sort_order` integer on `decision` and
`risk` so their board/list can be reordered. Existing rows default to 0, which
preserves today's ordering (newest-first / by-severity) as the tiebreak.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "decision",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "risk",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("risk", "sort_order")
    op.drop_column("decision", "sort_order")
