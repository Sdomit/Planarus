"""Widen doc CHECKs for canvas docs (Phase 13)

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-16

Additive: widen ``ck_doc_doc_type`` to include ``'canvas'`` and ``ck_doc_format``
to include ``'excalidraw'`` so a Doc can represent an Excalidraw whiteboard
(``doc_type='canvas'``, ``editor_format='excalidraw'``). No column or table added;
existing docs are unaffected.

SQLite-safe: the CHECK change uses Alembic batch (table recreate). CHECK value
lists are frozen snapshots — do not import runtime constants into a migration.

Downgrade refuses to delete data: it raises a clear error if any canvas doc still
exists, rather than silently violating the narrowed CHECK.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DOC_TYPE_OLD = "doc_type IN ('note', 'spec', 'research', 'plan', 'reference', 'other')"
_DOC_TYPE_NEW = (
    "doc_type IN ('note', 'spec', 'research', 'plan', 'reference', 'other', 'canvas')"
)
_DOC_FORMAT_OLD = "editor_format IN ('tiptap_json')"
_DOC_FORMAT_NEW = "editor_format IN ('tiptap_json', 'excalidraw')"


def upgrade() -> None:
    with op.batch_alter_table("doc") as batch_op:
        batch_op.drop_constraint("ck_doc_doc_type", type_="check")
        batch_op.create_check_constraint("ck_doc_doc_type", _DOC_TYPE_NEW)
        batch_op.drop_constraint("ck_doc_format", type_="check")
        batch_op.create_check_constraint("ck_doc_format", _DOC_FORMAT_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM doc "
            "WHERE doc_type = 'canvas' OR editor_format = 'excalidraw'"
        )
    ).scalar()
    if n:
        raise RuntimeError(
            f"refusing to downgrade 0013: {n} canvas doc(s) exist; convert or "
            "delete them before narrowing the doc CHECKs"
        )
    with op.batch_alter_table("doc") as batch_op:
        batch_op.drop_constraint("ck_doc_doc_type", type_="check")
        batch_op.create_check_constraint("ck_doc_doc_type", _DOC_TYPE_OLD)
        batch_op.drop_constraint("ck_doc_format", type_="check")
        batch_op.create_check_constraint("ck_doc_format", _DOC_FORMAT_OLD)
