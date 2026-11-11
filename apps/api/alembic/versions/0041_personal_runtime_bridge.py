"""Reconcile personal-runtime databases that used private revision numbers.

The personal installation already has planning/link approvals and preview
columns under revisions 0036-0038. Its database can be stamped to public 0040
after a backup; this migration adds the public-only MCP activity and project
mode schema that those numbers skipped. Ordinary public upgrades are no-ops.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    if "mcp_activity" not in inspector.get_table_names():
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
        activity_indexes: set[str] = set()
    else:
        activity_indexes = {index["name"] for index in inspector.get_indexes("mcp_activity")}
    if "ix_mcp_activity_project_id" not in activity_indexes:
        op.create_index("ix_mcp_activity_project_id", "mcp_activity", ["project_id"])
    if "ix_mcp_activity_last_seen" not in activity_indexes:
        op.create_index("ix_mcp_activity_last_seen", "mcp_activity", ["last_seen_at"])

    if "mode" not in {column["name"] for column in inspector.get_columns("project")}:
        # Legacy projects already using MCP retain their Agentic capabilities.
        op.add_column(
            "project",
            sa.Column("mode", sa.String(length=16), nullable=False, server_default="agentic"),
        )
    if "ix_project_mode" not in {index["name"] for index in inspector.get_indexes("project")}:
        op.create_index("ix_project_mode", "project", ["mode"])


def downgrade() -> None:
    # These features originate in public 0036/0037 on ordinary installs. There
    # is no reliable marker for which installation created them in this bridge.
    pass
