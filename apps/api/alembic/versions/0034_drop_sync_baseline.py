"""Drop the syncbaseline table (#102 — retire the dead sync conflict engine)

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-26

Migration 0011 added this table for a three-way-diff conflict engine built
against a Phase 14 that was never built. Verified before removal: nothing in
`app/` outside `app/sync/` itself referenced `three_way_diff`,
`resolve_conflicts`, `apply_plan`, `load_baseline`, `save_baseline`, `SyncPlan`,
`Manifest`, `entity_signature`, `snapshot_manifest` or `export_records`, and the
two wired routes (`/sync/snapshot`, `/sync/push`) had no caller in the web
client, the scripts, or the guides.

The downgrade recreates the table exactly as 0011 did, so this is reversible —
but the rows are gone. That is acceptable because the table was only ever written
by a sync run, and sync was never run: nothing called the endpoints that write it.

Numbering: this was authored as 0033 when `main`'s head was 0032, and so was
PR #110's `0033_entity_connections`. #110 landed first, so this one renumbered to
0034 on top of it — `alembic heads` was run against the rebased tree rather than
the number being incremented blindly.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_syncbaseline_project_id", table_name="syncbaseline")
    op.drop_table("syncbaseline")


def downgrade() -> None:
    # Byte-for-byte the shape 0011 created, so a downgrade lands on the schema
    # every earlier revision expects.
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
