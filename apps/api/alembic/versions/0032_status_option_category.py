"""Give a custom status a semantic category (#88)

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-24

Additive: one `category` column on `status_option`, NOT NULL with a server
default of `open` and a CHECK of (open, done, canceled). SQLite-safe via Alembic
batch (table recreate), like 0025; the table's named unique constraint, its
entity_type CHECK and its indexes are reflected and recreated by the batch.

Every existing row backfills to `open`, which is exactly how a custom status
behaved before this column existed — the roadmap, the notification feed and the
agent brief all compared against the literal strings `done`/`canceled`, so
nothing custom ever counted as finished. The column changes no behavior on its
own; it lets a project *say* that its "Shipped" column means done.

CHECK value lists are frozen snapshots — do not import runtime constants into a
migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshot of app/core/constants.py STATUS_CATEGORIES at 0032.
_CATEGORIES = "'open', 'done', 'canceled'"


def upgrade() -> None:
    with op.batch_alter_table("status_option") as batch_op:
        batch_op.add_column(
            sa.Column("category", sa.String(), nullable=False, server_default="open")
        )
        batch_op.create_check_constraint(
            "ck_status_option_category", f"category IN ({_CATEGORIES})"
        )


def downgrade() -> None:
    with op.batch_alter_table("status_option") as batch_op:
        batch_op.drop_constraint("ck_status_option_category", type_="check")
        batch_op.drop_column("category")
