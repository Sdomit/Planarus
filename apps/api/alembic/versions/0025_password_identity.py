"""Local email+password provider (Phase 11.1, D25)

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-18

Additive: one nullable ``password_hash`` column on ``useridentity`` (the Argon2id
verifier, set only on ``password`` provider rows) and a widened
``ck_useridentity_provider`` CHECK accepting ``'password'``. SQLite-safe via
Alembic batch (table recreate); ``useridentity``'s named unique constraint and
plain index are reflected and recreated by the batch. CHECK value lists are
frozen snapshots — do not import runtime constants into a migration.

Downgrade refuses to delete data (0016 discipline): it raises a clear error if
any password identity rows still exist, rather than silently dropping their
credential and violating the narrowed CHECK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshots of app/core/constants.py AUTH_PROVIDERS (0010 → here).
_PROVIDERS_OLD = "'dev', 'google', 'github'"
_PROVIDERS_NEW = "'dev', 'google', 'github', 'password'"


def upgrade() -> None:
    with op.batch_alter_table("useridentity") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(), nullable=True))
        batch_op.drop_constraint("ck_useridentity_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_useridentity_provider", f"provider IN ({_PROVIDERS_NEW})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(
        sa.text("SELECT COUNT(*) FROM useridentity WHERE provider = 'password'")
    ).scalar()
    if n:
        raise RuntimeError(
            f"refusing to downgrade 0025: {n} password identity row(s) exist; "
            "remove them before narrowing the provider CHECK"
        )
    with op.batch_alter_table("useridentity") as batch_op:
        batch_op.drop_constraint("ck_useridentity_provider", type_="check")
        batch_op.create_check_constraint(
            "ck_useridentity_provider", f"provider IN ({_PROVIDERS_OLD})"
        )
        batch_op.drop_column("password_hash")
