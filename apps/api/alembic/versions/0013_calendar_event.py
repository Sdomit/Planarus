"""CalendarEvent table (Phase 15.12a — calendar surface)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-16

Additive only: one new `calendar_event` table with a frozen status CHECK and two
indexes. No existing table, CHECK, or index changes. `external_uid`/`etag` are
reserved for external provider sync (15.12c/d) and ship nullable/unused.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshot of CALENDAR_EVENT_STATUSES at authoring time (do NOT import the
# runtime constant into a migration).
_CALENDAR_EVENT_STATUSES = "'confirmed', 'tentative', 'cancelled'"


def upgrade() -> None:
    op.create_table(
        "calendar_event",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("phase_id", sa.String(), sa.ForeignKey("phase.id"), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="confirmed"),
        sa.Column("start_at", sa.String(), nullable=False),
        sa.Column("end_at", sa.String(), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_uid", sa.String(), nullable=True),
        sa.Column("etag", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_CALENDAR_EVENT_STATUSES})",
            name="ck_calendar_event_status",
        ),
    )
    op.create_index(
        "ix_calendar_event_project_id", "calendar_event", ["project_id"]
    )
    op.create_index(
        "ix_calendar_event_phase_id", "calendar_event", ["phase_id"]
    )
    op.create_index(
        "ix_calendar_event_external_uid", "calendar_event", ["external_uid"]
    )
    op.create_index(
        "ix_calendar_event_project_start",
        "calendar_event",
        ["project_id", "start_at"],
    )
    op.create_index(
        "ix_calendar_event_project_sort",
        "calendar_event",
        ["project_id", "sort_order"],
    )


def downgrade() -> None:
    op.drop_index("ix_calendar_event_project_sort", table_name="calendar_event")
    op.drop_index("ix_calendar_event_project_start", table_name="calendar_event")
    op.drop_index("ix_calendar_event_external_uid", table_name="calendar_event")
    op.drop_index("ix_calendar_event_phase_id", table_name="calendar_event")
    op.drop_index("ix_calendar_event_project_id", table_name="calendar_event")
    op.drop_table("calendar_event")
