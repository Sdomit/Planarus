"""Add the mention table (#138/plan 23 — entity @mention backlinks).

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-27

A doc's `content_json` is the only author of these rows: `doc_service`
full-replaces a doc's mentions on every save by parsing its `mention` Tiptap
nodes server-side. No POST/PATCH endpoint exists — read-only, like a link's
reverse would be if one existed.

`target_type` reuses the same allowlist Link's `entity_type` already checks
(REF_ENTITY_TYPES) via `link_entity_type_check_sql`, just aimed at this
column's name.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET_TYPES = (
    "'project', 'phase', 'stage', 'task', 'decision', 'risk', 'blocker', "
    "'milestone', 'doc', 'calendar_event'"
)


def upgrade() -> None:
    op.create_table(
        "mention",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("source_doc_id", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint(f"target_type IN ({_TARGET_TYPES})", name="ck_mention_target_type"),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["source_doc_id"], ["doc.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mention_project_id", "mention", ["project_id"])
    op.create_index("ix_mention_target", "mention", ["target_type", "target_id"])
    op.create_index("ix_mention_source_doc", "mention", ["source_doc_id"])


def downgrade() -> None:
    op.drop_index("ix_mention_source_doc", table_name="mention")
    op.drop_index("ix_mention_target", table_name="mention")
    op.drop_index("ix_mention_project_id", table_name="mention")
    op.drop_table("mention")
