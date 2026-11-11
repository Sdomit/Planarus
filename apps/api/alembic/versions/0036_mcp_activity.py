"""Add short-lived, project-scoped MCP activity markers."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mcp_activity",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("actor_ref", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_ref", "project_id", name="uq_mcp_activity_actor_project"),
    )
    op.create_index("ix_mcp_activity_project_id", "mcp_activity", ["project_id"])
    op.create_index("ix_mcp_activity_last_seen", "mcp_activity", ["last_seen_at"])


def downgrade() -> None:
    op.drop_index("ix_mcp_activity_last_seen", table_name="mcp_activity")
    op.drop_index("ix_mcp_activity_project_id", table_name="mcp_activity")
    op.drop_table("mcp_activity")
