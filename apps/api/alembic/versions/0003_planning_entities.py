"""Planning entities: Phase, Stage, Task, Decision, Risk, Blocker

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19

Additive migration — creates 6 new tables. No ALTER TABLE on existing tables.
CHECK values are frozen snapshots; keep in sync with app/core/constants.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen CHECK value lists (do not import from constants — migration is a snapshot).
_PHASE_STATUSES = "'planned', 'active', 'blocked', 'done', 'canceled'"
_TASK_STATUSES = (
    "'backlog', 'ready', 'in_progress', 'waiting', 'needs_review',"
    " 'blocked', 'done', 'canceled'"
)
_TASK_PRIORITIES = "'low', 'med', 'high', 'urgent'"
_DECISION_STATUSES = "'proposed', 'accepted', 'superseded', 'reversed'"
_RISK_STATUSES = "'open', 'monitoring', 'mitigated', 'accepted', 'closed'"
_RISK_SEVERITIES = "'low', 'medium', 'high', 'critical'"
_BLOCKER_STATUSES = "'open', 'resolved', 'canceled'"


def upgrade() -> None:
    # 1. phase (FK → project)
    op.create_table(
        "phase",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"status IN ({_PHASE_STATUSES})", name="ck_phase_status"),
    )
    op.create_index("ix_phase_project_id", "phase", ["project_id"])
    op.create_index("ix_phase_project_sort", "phase", ["project_id", "sort_order"])
    op.create_index("ix_phase_project_status", "phase", ["project_id", "status"])

    # 2. stage (FK → phase, FK → project)
    op.create_table(
        "stage",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("phase_id", sa.String(), sa.ForeignKey("phase.id"), nullable=False),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"status IN ({_PHASE_STATUSES})", name="ck_stage_status"),
    )
    op.create_index("ix_stage_phase_id", "stage", ["phase_id"])
    op.create_index("ix_stage_project_id", "stage", ["project_id"])
    op.create_index("ix_stage_phase_sort", "stage", ["phase_id", "sort_order"])
    op.create_index("ix_stage_project_sort", "stage", ["project_id", "sort_order"])
    op.create_index("ix_stage_project_status", "stage", ["project_id", "status"])

    # 3. task (FK → project, phase, stage)
    op.create_table(
        "task",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("phase_id", sa.String(), sa.ForeignKey("phase.id"), nullable=True),
        sa.Column("stage_id", sa.String(), sa.ForeignKey("stage.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="backlog"),
        sa.Column("priority", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("due_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"status IN ({_TASK_STATUSES})", name="ck_task_status"),
        sa.CheckConstraint(
            f"priority IS NULL OR priority IN ({_TASK_PRIORITIES})",
            name="ck_task_priority",
        ),
    )
    op.create_index("ix_task_project_id", "task", ["project_id"])
    op.create_index("ix_task_phase_id", "task", ["phase_id"])
    op.create_index("ix_task_stage_id", "task", ["stage_id"])
    op.create_index("ix_task_project_status", "task", ["project_id", "status"])
    op.create_index(
        "ix_task_project_status_sort", "task", ["project_id", "status", "sort_order"]
    )

    # 4. decision (FK → project)
    op.create_table(
        "decision",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="proposed"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_DECISION_STATUSES})", name="ck_decision_status"
        ),
    )
    op.create_index("ix_decision_project_id", "decision", ["project_id"])
    op.create_index("ix_decision_project_status", "decision", ["project_id", "status"])
    op.create_index(
        "ix_decision_project_created", "decision", ["project_id", "created_at"]
    )

    # 5. risk (FK → project)
    op.create_table(
        "risk",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("mitigation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"status IN ({_RISK_STATUSES})", name="ck_risk_status"),
        sa.CheckConstraint(
            f"severity IN ({_RISK_SEVERITIES})", name="ck_risk_severity"
        ),
    )
    op.create_index("ix_risk_project_id", "risk", ["project_id"])
    op.create_index("ix_risk_project_status", "risk", ["project_id", "status"])
    op.create_index("ix_risk_project_severity", "risk", ["project_id", "severity"])

    # 6. blocker (FK → project, task)
    op.create_table(
        "blocker",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_BLOCKER_STATUSES})", name="ck_blocker_status"
        ),
    )
    op.create_index("ix_blocker_project_id", "blocker", ["project_id"])
    op.create_index("ix_blocker_task_id", "blocker", ["task_id"])
    op.create_index("ix_blocker_project_status", "blocker", ["project_id", "status"])


def downgrade() -> None:
    # Drop in reverse FK dependency order.
    op.drop_index("ix_blocker_project_status", table_name="blocker")
    op.drop_index("ix_blocker_task_id", table_name="blocker")
    op.drop_index("ix_blocker_project_id", table_name="blocker")
    op.drop_table("blocker")

    op.drop_index("ix_risk_project_severity", table_name="risk")
    op.drop_index("ix_risk_project_status", table_name="risk")
    op.drop_index("ix_risk_project_id", table_name="risk")
    op.drop_table("risk")

    op.drop_index("ix_decision_project_created", table_name="decision")
    op.drop_index("ix_decision_project_status", table_name="decision")
    op.drop_index("ix_decision_project_id", table_name="decision")
    op.drop_table("decision")

    op.drop_index("ix_task_project_status_sort", table_name="task")
    op.drop_index("ix_task_project_status", table_name="task")
    op.drop_index("ix_task_stage_id", table_name="task")
    op.drop_index("ix_task_phase_id", table_name="task")
    op.drop_index("ix_task_project_id", table_name="task")
    op.drop_table("task")

    op.drop_index("ix_stage_project_status", table_name="stage")
    op.drop_index("ix_stage_project_sort", table_name="stage")
    op.drop_index("ix_stage_phase_sort", table_name="stage")
    op.drop_index("ix_stage_project_id", table_name="stage")
    op.drop_index("ix_stage_phase_id", table_name="stage")
    op.drop_table("stage")

    op.drop_index("ix_phase_project_status", table_name="phase")
    op.drop_index("ix_phase_project_sort", table_name="phase")
    op.drop_index("ix_phase_project_id", table_name="phase")
    op.drop_table("phase")
