"""Milestone, ChecklistItem, Comment, Link tables (Phase 4b — finish MVP data model)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-13

Additive only: four new tables that complete the Must-have MVP data model
(03-data-model.md) — dated project milestones, per-task checklist items, and the
polymorphic Comment/Link attachments. No existing table, CHECK, or index changes.
CHECK value lists are frozen snapshots — do not import runtime constants here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen CHECK value lists (snapshots of app/core/constants.py at authoring time).
_MILESTONE_STATUSES = "'planned', 'active', 'achieved', 'missed', 'canceled'"
_REF_ENTITY_TYPES = (
    "'project', 'phase', 'stage', 'task', 'decision', 'risk', 'blocker', "
    "'milestone', 'doc'"
)
_COMMENT_AUTHOR_TYPES = "'human', 'agent', 'system'"


def upgrade() -> None:
    # 1. milestone (FK → project, phase)
    op.create_table(
        "milestone",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("phase_id", sa.String(), sa.ForeignKey("phase.id"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="planned"),
        sa.Column("target_date", sa.String(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"status IN ({_MILESTONE_STATUSES})", name="ck_milestone_status"
        ),
    )
    op.create_index("ix_milestone_project_id", "milestone", ["project_id"])
    op.create_index("ix_milestone_phase_id", "milestone", ["phase_id"])
    op.create_index("ix_milestone_project_status", "milestone", ["project_id", "status"])
    op.create_index("ix_milestone_project_sort", "milestone", ["project_id", "sort_order"])

    # 2. checklistitem (FK → task)
    op.create_table(
        "checklistitem",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("task_id", sa.String(), sa.ForeignKey("task.id"), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_checklistitem_task_id", "checklistitem", ["task_id"])
    op.create_index("ix_checklistitem_task_sort", "checklistitem", ["task_id", "sort_order"])

    # 3. comment (FK → project; polymorphic entity ref)
    op.create_table(
        "comment",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_type", sa.String(), nullable=False, server_default="human"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"entity_type IN ({_REF_ENTITY_TYPES})", name="ck_comment_entity_type"
        ),
        sa.CheckConstraint(
            f"author_type IN ({_COMMENT_AUTHOR_TYPES})", name="ck_comment_author_type"
        ),
    )
    op.create_index("ix_comment_project_id", "comment", ["project_id"])
    op.create_index("ix_comment_entity", "comment", ["entity_type", "entity_id"])
    op.create_index("ix_comment_project_created", "comment", ["project_id", "created_at"])

    # 4. link (FK → project; polymorphic entity ref)
    op.create_table(
        "link",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("url", sa.String(2000), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"entity_type IN ({_REF_ENTITY_TYPES})", name="ck_link_entity_type"
        ),
    )
    op.create_index("ix_link_project_id", "link", ["project_id"])
    op.create_index("ix_link_entity", "link", ["entity_type", "entity_id"])
    op.create_index("ix_link_project_created", "link", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_link_project_created", table_name="link")
    op.drop_index("ix_link_entity", table_name="link")
    op.drop_index("ix_link_project_id", table_name="link")
    op.drop_table("link")

    op.drop_index("ix_comment_project_created", table_name="comment")
    op.drop_index("ix_comment_entity", table_name="comment")
    op.drop_index("ix_comment_project_id", table_name="comment")
    op.drop_table("comment")

    op.drop_index("ix_checklistitem_task_sort", table_name="checklistitem")
    op.drop_index("ix_checklistitem_task_id", table_name="checklistitem")
    op.drop_table("checklistitem")

    op.drop_index("ix_milestone_project_sort", table_name="milestone")
    op.drop_index("ix_milestone_project_status", table_name="milestone")
    op.drop_index("ix_milestone_phase_id", table_name="milestone")
    op.drop_index("ix_milestone_project_id", table_name="milestone")
    op.drop_table("milestone")
