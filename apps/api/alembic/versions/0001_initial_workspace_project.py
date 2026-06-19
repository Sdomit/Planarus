"""Initial Workspace, Project, AuditEvent tables

Revision ID: 0001
Revises:
Create Date: 2026-06-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_project_root", sa.String(), nullable=True),
        sa.Column("settings_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_workspace_slug", "workspace", ["slug"], unique=True)

    op.create_table(
        "project",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspace.id"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("project_type", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="idea"),
        sa.Column("priority", sa.String(), nullable=True),
        sa.Column("folder_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_project_workspace_slug"),
    )
    op.create_index("ix_project_workspace_id", "project", ["workspace_id"])
    op.create_index("ix_project_status", "project", ["status"])

    op.create_table(
        "auditevent",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("workspace_id", sa.String(), sa.ForeignKey("workspace.id"), nullable=True),
        sa.Column("project_id", sa.String(), sa.ForeignKey("project.id"), nullable=True),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("ix_auditevent_workspace_id", "auditevent", ["workspace_id"])
    op.create_index("ix_auditevent_project_id", "auditevent", ["project_id"])
    op.create_index(
        "ix_auditevent_entity", "auditevent", ["entity_type", "entity_id"]
    )


def downgrade() -> None:
    op.drop_table("auditevent")
    op.drop_index("ix_project_status", table_name="project")
    op.drop_index("ix_project_workspace_id", table_name="project")
    op.drop_table("project")
    op.drop_index("ix_workspace_slug", table_name="workspace")
    op.drop_table("workspace")
