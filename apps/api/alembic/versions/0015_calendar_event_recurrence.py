"""CalendarEvent recurrence columns (Phase 15.12b — recurring events)

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-17

Additive only: two new nullable/defaulted columns on `calendar_event`:
`recurrence` (none|daily|weekly|monthly, defaults 'none') and `recurrence_until`
(inclusive YYYY-MM-DD, nullable). No CHECK is added at the DB level — the value
set is validated in the schema layer — so this stays a plain add_column with no
SQLite batch table-recreate. Existing rows get recurrence='none'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "calendar_event",
        sa.Column("recurrence", sa.String(), nullable=False, server_default="none"),
    )
    op.add_column(
        "calendar_event",
        sa.Column("recurrence_until", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("calendar_event", "recurrence_until")
    op.drop_column("calendar_event", "recurrence")
