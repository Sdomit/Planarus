"""Identity + workspace membership tables (Phase 10.1 — hosted mode)

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-15

Additive only: four new tables for the hosted-mode identity layer — ``appuser``
(``user`` is reserved in Postgres), ``useridentity`` (linked login providers),
``workspacemember`` (workspace-scoped RBAC role), and ``usersession`` (server-side
sessions; only a token hash is stored). No existing table, CHECK, or index
changes. Everything here is inert until ``AGENTBOARD_AUTH_ENABLED`` is set.

Dialect-portable (P10.0 discipline): bare boolean predicates and ``sa.true()``
defaults only. CHECK value lists are frozen snapshots — do not import runtime
constants here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen snapshots of app/core/constants.py at authoring time.
_WORKSPACE_ROLES = "'owner', 'editor', 'viewer'"
_AUTH_PROVIDERS = "'dev', 'google', 'github'"


def upgrade() -> None:
    # 1. appuser
    op.create_table(
        "appuser",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_appuser_email", "appuser", ["email"], unique=True)

    # 2. useridentity (FK → appuser; one row per linked login provider)
    op.create_table(
        "useridentity",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("appuser.id"), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("provider_subject", sa.String(320), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_useridentity_provider_subject"
        ),
        sa.CheckConstraint(
            f"provider IN ({_AUTH_PROVIDERS})", name="ck_useridentity_provider"
        ),
    )
    op.create_index("ix_useridentity_user_id", "useridentity", ["user_id"])

    # 3. workspacemember (FK → workspace, appuser; workspace-scoped RBAC role)
    op.create_table(
        "workspacemember",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(), sa.ForeignKey("workspace.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(), sa.ForeignKey("appuser.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "user_id", name="uq_workspacemember_ws_user"
        ),
        sa.CheckConstraint(
            f"role IN ({_WORKSPACE_ROLES})", name="ck_workspacemember_role"
        ),
    )
    op.create_index(
        "ix_workspacemember_workspace_id", "workspacemember", ["workspace_id"]
    )
    op.create_index("ix_workspacemember_user_id", "workspacemember", ["user_id"])

    # 4. usersession (FK → appuser; only a token hash is stored)
    op.create_table(
        "usersession",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("appuser.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("expires_at", sa.String(), nullable=False),
        sa.Column("last_seen_at", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_usersession_token_hash", "usersession", ["token_hash"], unique=True
    )
    op.create_index("ix_usersession_user_id", "usersession", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_usersession_user_id", table_name="usersession")
    op.drop_index("ix_usersession_token_hash", table_name="usersession")
    op.drop_table("usersession")

    op.drop_index("ix_workspacemember_user_id", table_name="workspacemember")
    op.drop_index("ix_workspacemember_workspace_id", table_name="workspacemember")
    op.drop_table("workspacemember")

    op.drop_index("ix_useridentity_user_id", table_name="useridentity")
    op.drop_table("useridentity")

    op.drop_index("ix_appuser_email", table_name="appuser")
    op.drop_table("appuser")
