from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import link_entity_type_check_sql


class Mention(SQLModel, table=True):
    """Derived @mention backlink row (#138/plan 23).

    Never authored directly: `doc_service.create_doc`/`update_doc` full-replace a
    doc's rows on every save by parsing `content_json` server-side. Reuses the
    entity-type allowlist Link/Comment already check against (REF_ENTITY_TYPES),
    just aimed at this table's `target_type` column instead of `entity_type`.
    """

    __tablename__ = "mention"
    __table_args__ = (
        CheckConstraint(link_entity_type_check_sql(column="target_type"), name="ck_mention_target_type"),
        Index("ix_mention_target", "target_type", "target_id"),
        Index("ix_mention_source_doc", "source_doc_id"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    source_doc_id: str = Field(foreign_key="doc.id")
    target_type: str
    target_id: str
    created_at: str
