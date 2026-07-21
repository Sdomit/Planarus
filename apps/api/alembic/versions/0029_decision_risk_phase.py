"""Link decisions and risks to a phase (Phase 19 — planning graph, D45)

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-21

Additive only: one nullable `phase_id` FK + index on `decision` and on `risk`,
mirroring the `milestone.phase_id` shape that has existed since 0009. Makes the
phase the spine of Planarus's planning graph — a phase can now roll up its
decisions and risks alongside its tasks and milestones.

Nullable on purpose (D45): cross-cutting decisions/risks stay at project level
rather than being mis-filed under one phase. Existing rows get NULL, which is
exactly that state, so there is no backfill and no behavior change for them.

Batch mode throughout — SQLite cannot ALTER a table to add a constraint in
place; this follows the 0026 `task.assignee_id` precedent.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decision") as batch:
        batch.add_column(sa.Column("phase_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_decision_phase_id", "phase", ["phase_id"], ["id"])
    op.create_index("ix_decision_phase_id", "decision", ["phase_id"])

    with op.batch_alter_table("risk") as batch:
        batch.add_column(sa.Column("phase_id", sa.String(), nullable=True))
        batch.create_foreign_key("fk_risk_phase_id", "phase", ["phase_id"], ["id"])
    op.create_index("ix_risk_phase_id", "risk", ["phase_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_phase_id", table_name="risk")
    with op.batch_alter_table("risk") as batch:
        batch.drop_constraint("fk_risk_phase_id", type_="foreignkey")
        batch.drop_column("phase_id")

    op.drop_index("ix_decision_phase_id", table_name="decision")
    with op.batch_alter_table("decision") as batch:
        batch.drop_constraint("fk_decision_phase_id", type_="foreignkey")
        batch.drop_column("phase_id")
