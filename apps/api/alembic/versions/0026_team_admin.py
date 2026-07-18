"""Team administration & attribution columns (Phase 16.1, D29/D33)

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-18

Additive only, five nullable-or-defaulted columns across five tables:

* ``appuser.is_admin`` (D29) — server-admin axis; existing rows stay non-admin.
* ``useridentity.password_must_change`` (D29) — admin-issued temp passwords.
* ``task.assignee_id`` / ``comment.author_id`` / ``doc.updated_by`` (D33) —
  nullable FKs to ``appuser`` (0020 discipline: batch add + named FK), write
  paths land in P16.3; existing rows are all unattributed (NULL).

SQLite-safe via Alembic batch (table recreate). Booleans get a server_default
so the NOT NULL add works on populated tables; the app layer always writes the
value explicitly.

Downgrade drops the columns. Unlike 0025 there is no CHECK to renarrow and the
columns are decorative attribution/authority flags, so a data-preserving refusal
would protect nothing the audit trail doesn't already hold.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("appuser") as batch:
        batch.add_column(
            sa.Column(
                "is_admin", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    with op.batch_alter_table("useridentity") as batch:
        batch.add_column(
            sa.Column(
                "password_must_change",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
    with op.batch_alter_table("task") as batch:
        batch.add_column(sa.Column("assignee_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_task_assignee_id", "appuser", ["assignee_id"], ["id"]
        )
    op.create_index("ix_task_assignee_id", "task", ["assignee_id"])
    with op.batch_alter_table("comment") as batch:
        batch.add_column(sa.Column("author_id", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_comment_author_id", "appuser", ["author_id"], ["id"]
        )
    with op.batch_alter_table("doc") as batch:
        batch.add_column(sa.Column("updated_by", sa.String(), nullable=True))
        batch.create_foreign_key(
            "fk_doc_updated_by", "appuser", ["updated_by"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("doc") as batch:
        batch.drop_constraint("fk_doc_updated_by", type_="foreignkey")
        batch.drop_column("updated_by")
    with op.batch_alter_table("comment") as batch:
        batch.drop_constraint("fk_comment_author_id", type_="foreignkey")
        batch.drop_column("author_id")
    op.drop_index("ix_task_assignee_id", table_name="task")
    with op.batch_alter_table("task") as batch:
        batch.drop_constraint("fk_task_assignee_id", type_="foreignkey")
        batch.drop_column("assignee_id")
    with op.batch_alter_table("useridentity") as batch:
        batch.drop_column("password_must_change")
    with op.batch_alter_table("appuser") as batch:
        batch.drop_column("is_admin")
