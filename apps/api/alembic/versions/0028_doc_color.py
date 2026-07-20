"""Add color to doc (note cards — Google-Keep-style swatches)

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-20

Additive only: one nullable `color` column on `doc`, holding a palette key
(`yellow`, `sage`, …) — not a hex value, so themes own the actual colors and
light/dark each render their own shade. NULL means the default surface, which
is what every existing row gets. No index: notes are listed per project and the
column is display-only, never filtered on.

Free-form nullable string, matching the `status_option.color` precedent; the
allowed keys are enforced in the schema layer, not by a CHECK constraint, so
adding a swatch later needs no migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("doc", sa.Column("color", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("doc", "color")
