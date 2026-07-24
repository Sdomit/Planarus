from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import doc_format_check_sql, doc_status_check_sql, doc_type_check_sql


class Doc(SQLModel, table=True):
    __tablename__ = "doc"
    __table_args__ = (
        CheckConstraint(doc_type_check_sql(), name="ck_doc_doc_type"),
        CheckConstraint(doc_format_check_sql(), name="ck_doc_format"),
        CheckConstraint(doc_status_check_sql(), name="ck_doc_status"),
        Index("ix_doc_project_id", "project_id"),
        Index("ix_doc_parent_doc_id", "parent_doc_id"),
        # Migration 0004 built this as a unique Index, not a UniqueConstraint;
        # declared the same way here so autogenerate does not swap one for the other.
        Index("uq_doc_project_slug", "project_id", "slug", unique=True),
        Index("ix_doc_project_type", "project_id", "doc_type"),
        Index("ix_doc_project_status", "project_id", "status"),
        Index("ix_doc_project_sort", "project_id", "sort_order"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    parent_doc_id: Optional[str] = Field(default=None, foreign_key="doc.id")
    title: str = Field(max_length=200)
    slug: str
    doc_type: str
    editor_format: str = Field(default="tiptap_json")
    content_json: str = Field(
        default='{"type": "doc", "content": [{"type": "paragraph"}]}'
    )
    markdown_cache: str = Field(default="")
    export_relative_path: Optional[str] = None
    export_checksum: Optional[str] = None
    exported_at: Optional[str] = None
    status: str = Field(default="draft")
    # Note-card swatch key (0028): NULL = default surface. See DOC_COLORS.
    color: Optional[str] = Field(default=None)
    sort_order: int = Field(default=0)
    version: int = Field(default=1)
    # P16.1 (D33): who last saved it, when a signed-in user did; wired in P16.3.
    updated_by: Optional[str] = Field(default=None, foreign_key="appuser.id")
    created_at: str
    updated_at: str
    archived_at: Optional[str] = None

    @property
    def excerpt(self) -> str:
        """First few lines of the body, for note/doc cards. Derived, never stored.

        ponytail: markdown_cache is already the client-serialized body, so a slice
        of it is the whole preview — no new column, no server-side ProseMirror parse.
        """
        return self.markdown_cache[:280]
