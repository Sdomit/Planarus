"""Extend custom statuses to phases and risks (Phase 15.5 follow-up)

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-17

Drops the `status` CHECK on `phase` and `risk` (custom statuses, validated in the
service layer) and widens the `status_option.entity_type` CHECK to allow
'phase' and 'risk'. Additive for data: existing rows keep their statuses.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshots for the downgrade CHECK re-creation.
_PHASE_STATUSES = "'planned', 'active', 'blocked', 'done', 'canceled'"
_RISK_STATUSES = "'open', 'monitoring', 'mitigated', 'accepted', 'closed'"


def upgrade() -> None:
    with op.batch_alter_table("phase") as batch:
        batch.drop_constraint("ck_phase_status", type_="check")
    with op.batch_alter_table("risk") as batch:
        batch.drop_constraint("ck_risk_status", type_="check")
    with op.batch_alter_table("status_option") as batch:
        batch.drop_constraint("ck_status_option_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_status_option_entity_type",
            "entity_type IN ('task', 'phase', 'risk')",
        )


def downgrade() -> None:
    with op.batch_alter_table("status_option") as batch:
        batch.drop_constraint("ck_status_option_entity_type", type_="check")
        batch.create_check_constraint(
            "ck_status_option_entity_type", "entity_type IN ('task')"
        )
    with op.batch_alter_table("risk") as batch:
        batch.create_check_constraint(
            "ck_risk_status", f"status IN ({_RISK_STATUSES})"
        )
    with op.batch_alter_table("phase") as batch:
        batch.create_check_constraint(
            "ck_phase_status", f"status IN ({_PHASE_STATUSES})"
        )
