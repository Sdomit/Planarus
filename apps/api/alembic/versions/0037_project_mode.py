"""Add an explicit Normal/Agentic capability mode to projects."""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A server default backfills existing rows. It intentionally remains in
    # place: SQLite cannot drop a column default without rebuilding the table,
    # and retaining ``agentic`` is the safe compatibility default for direct or
    # legacy inserts. The public create API explicitly defaults new projects to
    # ``normal``.
    op.add_column(
        "project",
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="agentic"),
    )
    op.create_index("ix_project_mode", "project", ["mode"])


def downgrade() -> None:
    op.drop_index("ix_project_mode", table_name="project")
    op.drop_column("project", "mode")
