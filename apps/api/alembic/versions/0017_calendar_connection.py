"""CalendarConnection token table (Phase 15.12b — external calendar sync)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-17

Additive only: one new `calendar_connection` table holding an external calendar
link per project. Access/refresh tokens are stored ENCRYPTED (Fernet) — this
migration only creates the columns; the app never writes plaintext here. Frozen
CHECK snapshots for provider (google|microsoft) and status
(connected|error|revoked). No existing table is touched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROVIDERS = "'google', 'microsoft'"
_STATUSES = "'connected', 'error', 'revoked'"


def upgrade() -> None:
    op.create_table(
        "calendar_connection",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("account_email", sa.String(), nullable=False),
        sa.Column("access_token_enc", sa.String(), nullable=False),
        sa.Column("refresh_token_enc", sa.String(), nullable=True),
        sa.Column("token_expiry", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="connected"),
        sa.Column("sync_token", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"provider IN ({_PROVIDERS})", name="ck_calconn_provider"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_calconn_status"),
    )
    op.create_index("ix_calendar_connection_project", "calendar_connection", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_calendar_connection_project", table_name="calendar_connection")
    op.drop_table("calendar_connection")
