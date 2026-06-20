from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DOC_FORMATS, DOC_STATUSES, DOC_TYPES

_DOC_TYPES = frozenset(DOC_TYPES)
_DOC_STATUSES = frozenset(DOC_STATUSES)
_DOC_FORMATS = frozenset(DOC_FORMATS)

_MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2 MB


class DocCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    doc_type: str
    status: str = "draft"
    sort_order: int = 0
    parent_doc_id: Optional[str] = None
    slug: Optional[str] = None  # frontend override; server re-deduplicates

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        if v not in _DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {', '.join(sorted(_DOC_TYPES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _DOC_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_DOC_STATUSES))}")
        return v


class DocUpdate(BaseModel):
    version: int  # required for all updates — optimistic concurrency guard
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    doc_type: Optional[str] = None
    status: Optional[str] = None
    sort_order: Optional[int] = None
    parent_doc_id: Optional[str] = None
    content_json: Optional[str] = None
    markdown_cache: Optional[str] = None
    archived_at: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {', '.join(sorted(_DOC_TYPES))}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DOC_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_DOC_STATUSES))}")
        return v

    @field_validator("content_json")
    @classmethod
    def validate_content_json(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if len(v.encode("utf-8")) > _MAX_CONTENT_BYTES:
            raise ValueError("content_json exceeds the 2 MB size limit")
        import json
        try:
            json.loads(v)
        except Exception:
            raise ValueError("content_json must be valid JSON")
        return v


class DocSummary(BaseModel):
    id: str
    project_id: str
    parent_doc_id: Optional[str]
    title: str
    slug: str
    doc_type: str
    status: str
    sort_order: int
    version: int
    updated_at: str
    archived_at: Optional[str]

    model_config = {"from_attributes": True}


class DocRead(BaseModel):
    id: str
    project_id: str
    parent_doc_id: Optional[str]
    title: str
    slug: str
    doc_type: str
    editor_format: str
    content_json: str
    markdown_cache: str
    export_relative_path: Optional[str]
    export_checksum: Optional[str]
    exported_at: Optional[str]
    status: str
    sort_order: int
    version: int
    created_at: str
    updated_at: str
    archived_at: Optional[str]

    model_config = {"from_attributes": True}


class DocExportResponse(BaseModel):
    export_path: str
    was_changed: bool
    drift_detected: bool
    checksum: str
