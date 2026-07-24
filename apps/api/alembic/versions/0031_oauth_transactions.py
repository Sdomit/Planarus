"""Server-side one-time OAuth transactions (#113)

Revision ID: 0031
Revises: 0029
Create Date: 2026-07-24

Additive only: one new `oauthtransaction` table. Nothing existing is altered, so
every current row and query is untouched; the table is only written when an
OAuth login/link or a calendar connect is started.

Numbering: `alembic heads` on `main` is `0029`. `0030` is taken by the still-draft
entity-connections branch, so this takes `0031` with `0029` as its parent — the
two are siblings until that branch rebases, and whichever merges second must
re-parent onto the other. (#88 was pencilled in for `0031`; it is unstarted, so
it moves to `0032`.)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauthtransaction",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("state_hash", sa.String(), nullable=False),
        sa.Column("binder_hash", sa.String(), nullable=False),
        sa.Column("redirect_uri", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("consumed_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["appuser.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_oauthtransaction_state_hash", "oauthtransaction", ["state_hash"], unique=True
    )
    op.create_index(
        "ix_oauthtransaction_expires_at", "oauthtransaction", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_oauthtransaction_expires_at", table_name="oauthtransaction")
    op.drop_index("ix_oauthtransaction_state_hash", table_name="oauthtransaction")
    op.drop_table("oauthtransaction")
