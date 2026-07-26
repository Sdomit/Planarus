"""Add typed entity connections and widen the approval action CHECKs.

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-22

Connections are project-owned polymorphic endpoint pairs. Foreign keys are
intentionally limited to the project: the service validates the endpoint type,
existence, project ownership, relation matrix, uniqueness, and task dependency
cycles. This avoids an unbounded table per entity while keeping every connection
strictly inside its project.

Renumbered from `0030` on 2026-07-25: `main` reached `0032` while this branch
sat open (`0031` OAuth transactions, `0032` status-option categories), so the
original number now collides and `0029` is no longer the head. This branch must
therefore merge `main` before Alembic can resolve the chain at all — `0032` does
not exist on it yet.

The approval CHECK lists are frozen snapshots. SQLite needs a batch-recreate to
widen them; the active-only idempotency index is recreated explicitly so the
partial predicate survives.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE = "status IN ('pending', 'approved', 'applying', 'failed')"
_ACTION_OLD = (
    "action_type IN ('task.create', 'task.update', 'decision.create', 'doc.update')"
)
_ACTION_NEW = (
    "action_type IN ('task.create', 'task.update', 'decision.create', 'doc.update', "
    "'connection.create')"
)
_TARGET_OLD = (
    "target_entity_type IS NULL OR target_entity_type IN ('task', 'decision', 'doc')"
)
_TARGET_NEW = (
    "target_entity_type IS NULL OR target_entity_type IN "
    "('task', 'decision', 'doc', 'entity_connection')"
)
_ENTITY_TYPES = "'phase', 'task', 'decision', 'risk', 'milestone', 'doc'"
_RELATION_TYPES = (
    "'depends_on', 'implements', 'mitigates', 'contributes_to', 'references', 'related_to'"
)


def _swap_approval_checks(action_sql: str, target_sql: str) -> None:
    op.drop_index("uq_approval_active_idem", table_name="approvalrequest")
    with op.batch_alter_table("approvalrequest") as batch:
        batch.drop_constraint("ck_approval_action_type", type_="check")
        batch.create_check_constraint("ck_approval_action_type", action_sql)
        batch.drop_constraint("ck_approval_target_entity_type", type_="check")
        batch.create_check_constraint("ck_approval_target_entity_type", target_sql)
    op.create_index(
        "uq_approval_active_idem",
        "approvalrequest",
        ["origin", "actor_ref", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
        postgresql_where=sa.text(_ACTIVE),
    )


def upgrade() -> None:
    op.create_table(
        "entity_connection",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("relation_type", sa.String(), nullable=False),
        sa.Column("source_entity_type", sa.String(), nullable=False),
        sa.Column("source_entity_id", sa.String(), nullable=False),
        sa.Column("target_entity_type", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"relation_type IN ({_RELATION_TYPES})",
            name="ck_entity_connection_relation_type",
        ),
        sa.CheckConstraint(
            f"source_entity_type IN ({_ENTITY_TYPES})",
            name="ck_entity_connection_source_entity_type",
        ),
        sa.CheckConstraint(
            f"target_entity_type IN ({_ENTITY_TYPES})",
            name="ck_entity_connection_target_entity_type",
        ),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "relation_type",
            "source_entity_type",
            "source_entity_id",
            "target_entity_type",
            "target_entity_id",
            name="uq_entity_connection_canonical",
        ),
    )
    op.create_index("ix_entity_connection_project_id", "entity_connection", ["project_id"])
    op.create_index(
        "ix_entity_connection_project_source",
        "entity_connection",
        ["project_id", "source_entity_type", "source_entity_id"],
    )
    op.create_index(
        "ix_entity_connection_project_target",
        "entity_connection",
        ["project_id", "target_entity_type", "target_entity_id"],
    )
    _swap_approval_checks(_ACTION_NEW, _TARGET_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    connection_count = bind.execute(sa.text("SELECT COUNT(*) FROM entity_connection")).scalar()
    approval_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM approvalrequest "
            "WHERE action_type = 'connection.create' "
            "OR target_entity_type = 'entity_connection'"
        )
    ).scalar()
    if connection_count or approval_count:
        raise RuntimeError(
            "refusing to downgrade 0033: connection rows or connection approval rows "
            "exist; resolve them before removing typed connections"
        )
    _swap_approval_checks(_ACTION_OLD, _TARGET_OLD)
    op.drop_index("ix_entity_connection_project_target", table_name="entity_connection")
    op.drop_index("ix_entity_connection_project_source", table_name="entity_connection")
    op.drop_index("ix_entity_connection_project_id", table_name="entity_connection")
    op.drop_table("entity_connection")
