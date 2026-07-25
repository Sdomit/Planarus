from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import DOC_COLORS, DOC_FORMATS, DOC_STATUSES, DOC_TYPES

_DOC_TYPES = frozenset(DOC_TYPES)
_DOC_STATUSES = frozenset(DOC_STATUSES)
_DOC_FORMATS = frozenset(DOC_FORMATS)
_DOC_COLORS = frozenset(DOC_COLORS)

_MAX_CONTENT_BYTES = 2 * 1024 * 1024  # 2 MB

# #117: structural limits for rich-document JSON (Tiptap docs and Excalidraw
# scenes both land in `content_json`). Generous next to any real document — a
# deeply nested list is single digits deep and a big canvas is thousands of
# nodes, not a hundred thousand — but they bound the recursion every consumer
# does over this tree.
_MAX_JSON_DEPTH = 100
_MAX_JSON_NODES = 200_000


def _check_json_shape(value, field: str) -> None:
    """Reject JSON that is too deep or has too many nodes. Iterative on purpose:
    a recursive check would blow the stack on exactly the input it is meant to
    reject."""
    nodes = 0
    stack = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if depth > _MAX_JSON_DEPTH:
            raise ValueError(f"{field} nests deeper than {_MAX_JSON_DEPTH} levels")
        if nodes > _MAX_JSON_NODES:
            raise ValueError(f"{field} has more than {_MAX_JSON_NODES} nodes")
        if isinstance(node, dict):
            stack.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, list):
            stack.extend((v, depth + 1) for v in node)


class DocCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    doc_type: str
    editor_format: str = "tiptap_json"  # Phase 13: 'excalidraw' creates a canvas
    status: str = "draft"
    sort_order: int = 0
    parent_doc_id: Optional[str] = None
    slug: Optional[str] = None  # frontend override; server re-deduplicates
    color: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: str) -> str:
        if v not in _DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {', '.join(sorted(_DOC_TYPES))}")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DOC_COLORS:
            raise ValueError(f"color must be one of: {', '.join(sorted(_DOC_COLORS))}")
        return v

    @field_validator("editor_format")
    @classmethod
    def validate_editor_format(cls, v: str) -> str:
        if v not in _DOC_FORMATS:
            raise ValueError(
                f"editor_format must be one of: {', '.join(sorted(_DOC_FORMATS))}"
            )
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
    # NOTE: None means "unchanged" here, so a swatch is cleared with "default",
    # not null — see doc_service.update_doc.
    color: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def validate_doc_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _DOC_TYPES:
            raise ValueError(f"doc_type must be one of: {', '.join(sorted(_DOC_TYPES))}")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "default" and v not in _DOC_COLORS:
            raise ValueError(f"color must be one of: default, {', '.join(sorted(_DOC_COLORS))}")
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
            parsed = json.loads(v)
        except Exception:
            raise ValueError("content_json must be valid JSON")
        # #117: size alone does not bound the *shape*. A small payload can nest
        # thousands of levels deep, and every consumer that walks it recursively
        # — the Markdown serializer, the editor, a future exporter — recurses
        # with it.
        _check_json_shape(parsed, "content_json")
        return v

    @field_validator("markdown_cache")
    @classmethod
    def validate_markdown_cache(cls, v: Optional[str]) -> Optional[str]:
        """#117: `content_json` was capped and its derived twin was not.

        `markdown_cache` is sent by the frontend, stored verbatim and written
        into disk exports, so an unbounded one is an unbounded write.
        """
        if v is not None and len(v.encode("utf-8")) > _MAX_CONTENT_BYTES:
            raise ValueError("markdown_cache exceeds the 2 MB size limit")
        return v


class DocSummary(BaseModel):
    id: str
    project_id: str
    parent_doc_id: Optional[str]
    title: str
    slug: str
    doc_type: str
    editor_format: str
    status: str
    sort_order: int
    version: int
    updated_at: str
    archived_at: Optional[str]
    color: Optional[str] = None
    # Derived from markdown_cache (Doc.excerpt) so cards can show a body preview.
    excerpt: str = ""

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
    color: Optional[str] = None
    updated_by: Optional[str] = None
    # P16.3 (D33): who last saved it, resolved at read time; None in local mode.
    updated_by_display: Optional[str] = None
    created_at: str
    updated_at: str
    archived_at: Optional[str]

    model_config = {"from_attributes": True}


class DocExportResponse(BaseModel):
    export_path: str
    was_changed: bool
    drift_detected: bool
    checksum: str
