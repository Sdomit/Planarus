from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import COMMENT_AUTHOR_TYPES, COMMENT_STATUSES, REF_ENTITY_TYPES

_ENTITY_TYPES = frozenset(REF_ENTITY_TYPES)
_AUTHOR_TYPES = frozenset(COMMENT_AUTHOR_TYPES)
_COMMENT_STATUSES = frozenset(COMMENT_STATUSES)


class CommentCreate(BaseModel):
    entity_type: str
    entity_id: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=10000)
    author_type: str = "human"

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in _ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of: {', '.join(sorted(_ENTITY_TYPES))}"
            )
        return v

    @field_validator("author_type")
    @classmethod
    def validate_author_type(cls, v: str) -> str:
        if v not in _AUTHOR_TYPES:
            raise ValueError(
                f"author_type must be one of: {', '.join(sorted(_AUTHOR_TYPES))}"
            )
        return v


class CommentUpdate(BaseModel):
    body: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _COMMENT_STATUSES:
            raise ValueError(
                f"status must be one of: {', '.join(sorted(_COMMENT_STATUSES))}"
            )
        return v


class CommentRead(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    body: str
    author_type: str
    author_id: Optional[str] = None
    # P16.3 (D33): who wrote it, resolved at read time; None in local mode.
    author_display: Optional[str] = None
    status: str
    created_at: str
    updated_at: Optional[str]

    model_config = {"from_attributes": True}
