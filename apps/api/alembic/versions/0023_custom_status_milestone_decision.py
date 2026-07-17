"""Extend custom statuses to milestones and decisions (Phase 15.5 follow-up)

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-17

Drops the `status` CHECK on `milestone` and `decision` (custom statuses,
validated in the service layer) and widens the `status_option.entity_type` CHECK
to allow 'milestone' and 'decision'. Additive for data.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MILESTONE_STATUSES = "'planned', 'active', 'achieved', 'missed', 'canceled'"
_DECISION_STATUSES = "'proposed', 'accepted', 'superseded', 'reversed'"


def upgrade() -> None:
    with op.batch_alter_table("milestone") as batch:
        batch.drop_constraint("ck_milestone_status", type_="check")
    with op.batch_alter_table("decision") as batch:
        batch.drop_constraint("ck_decision_status", type_="check")
    with op.batch_alter_table("status_option") as batch:
        batch.drop_constraint("ck_status_option_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_status_option_entity_type",
            "entity_type IN ('task', 'phase', 'risk', 'milestone', 'decision')",
        )


def downgrade() -> None:
    with op.batch_alter_table("status_option") as batch:
        batch.drop_constraint("ck_status_option_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_status_option_entity_type",
            "entity_type IN ('task', 'phase', 'risk')",
        )
    with op.batch_alter_table("decision") as batch:
        batch.create_check_constraint(
            "ck_decision_status", f"status IN ({_DECISION_STATUSES})"
        )
    with op.batch_alter_table("milestone") as batch:
        batch.create_check_constraint(
            "ck_milestone_status", f"status IN ({_MILESTONE_STATUSES})"
        )
