"""Make comments editable + triageable (Phase 15.7)

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-16

Additive only: a `status` column (default 'active', CHECK active|done|attention)
and a nullable `updated_at` on `comment`. Existing rows default to 'active' with
a NULL `updated_at` (never edited). The old "append-only" comment contract is
intentionally relaxed here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMMENT_STATUSES = "'active', 'done', 'attention'"


def upgrade() -> None:
    op.add_column(
        "comment",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column("comment", sa.Column("updated_at", sa.String(), nullable=True))
    with op.batch_alter_table("comment") as batch:
        batch.create_check_constraint(
            "ck_comment_status", f"status IN ({_COMMENT_STATUSES})"
        )


def downgrade() -> None:
    with op.batch_alter_table("comment") as batch:
        batch.drop_constraint("ck_comment_status", type_="check")
    op.drop_column("comment", "updated_at")
    op.drop_column("comment", "status")
