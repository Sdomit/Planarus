"""Add bounded approval previews for readable queue rows.

Revision ID: 0040
Revises: 0039
"""

from __future__ import annotations

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("approvalrequest", sa.Column("proposed_title", sa.String(), nullable=True))
    op.add_column("approvalrequest", sa.Column("proposed_excerpt", sa.String(), nullable=True))
    conn = op.get_bind()
    # Historic records need the same labels. Skip canvas patches, whose scene
    # bodies can be huge and have no title/description to preview.
    rows = conn.execute(
        sa.text(
            "SELECT id, proposed_patch_json FROM approvalrequest WHERE action_type != 'doc.update'"
        )
    )
    update = sa.text(
        "UPDATE approvalrequest SET proposed_title = :title, proposed_excerpt = :excerpt WHERE id = :id"
    )
    while batch := rows.fetchmany(200):
        for approval_id, patch_json in batch:
            try:
                patch = json.loads(patch_json)
            except (TypeError, ValueError):
                continue
            if not isinstance(patch, dict):
                continue
            title = patch.get("title")
            excerpt = next(
                (
                    patch[key]
                    for key in ("description", "decision", "body", "context", "mitigation")
                    if isinstance(patch.get(key), str) and patch[key].strip()
                ),
                None,
            )
            conn.execute(
                update,
                {
                    "id": approval_id,
                    "title": " ".join(title.split())[:160] if isinstance(title, str) else None,
                    "excerpt": " ".join(excerpt.split())[:180] if excerpt else None,
                },
            )


def downgrade() -> None:
    op.drop_column("approvalrequest", "proposed_excerpt")
    op.drop_column("approvalrequest", "proposed_title")
