"""Doc: rich document entity

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-20

Additive migration — creates the `doc` table. No ALTER TABLE on existing tables.
CHECK values are frozen snapshots; keep in sync with app/core/constants.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen CHECK value lists (do not import from constants — migration is a snapshot).
_DOC_TYPES = "'note', 'spec', 'research', 'plan', 'reference', 'other'"
_DOC_FORMATS = "'tiptap_json'"
_DOC_STATUSES = "'draft', 'published'"

_EMPTY_DOC = '{"type": "doc", "content": [{"type": "paragraph"}]}'


def upgrade() -> None:
    op.create_table(
        "doc",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("project.id"),
            nullable=False,
        ),
        sa.Column(
            "parent_doc_id",
            sa.String(),
            sa.ForeignKey("doc.id"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column(
            "editor_format",
            sa.String(),
            nullable=False,
            server_default="tiptap_json",
        ),
        sa.Column(
            "content_json",
            sa.Text(),
            nullable=False,
            server_default=_EMPTY_DOC,
        ),
        sa.Column("markdown_cache", sa.Text(), nullable=False, server_default=""),
        sa.Column("export_relative_path", sa.String(), nullable=True),
        sa.Column("export_checksum", sa.String(), nullable=True),
        sa.Column("exported_at", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.CheckConstraint(f"doc_type IN ({_DOC_TYPES})", name="ck_doc_doc_type"),
        sa.CheckConstraint(f"editor_format IN ({_DOC_FORMATS})", name="ck_doc_format"),
        sa.CheckConstraint(f"status IN ({_DOC_STATUSES})", name="ck_doc_status"),
    )
    op.create_index("ix_doc_project_id", "doc", ["project_id"])
    op.create_index("ix_doc_parent_doc_id", "doc", ["parent_doc_id"])
    op.create_index("uq_doc_project_slug", "doc", ["project_id", "slug"], unique=True)
    op.create_index("ix_doc_project_type", "doc", ["project_id", "doc_type"])
    op.create_index("ix_doc_project_status", "doc", ["project_id", "status"])
    op.create_index("ix_doc_project_sort", "doc", ["project_id", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_doc_project_sort", table_name="doc")
    op.drop_index("ix_doc_project_status", table_name="doc")
    op.drop_index("ix_doc_project_type", table_name="doc")
    op.drop_index("uq_doc_project_slug", table_name="doc")
    op.drop_index("ix_doc_parent_doc_id", table_name="doc")
    op.drop_index("ix_doc_project_id", table_name="doc")
    op.drop_table("doc")
