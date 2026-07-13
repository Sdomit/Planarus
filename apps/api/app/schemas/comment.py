from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import COMMENT_AUTHOR_TYPES, REF_ENTITY_TYPES

_ENTITY_TYPES = frozenset(REF_ENTITY_TYPES)
_AUTHOR_TYPES = frozenset(COMMENT_AUTHOR_TYPES)


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


class CommentRead(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    body: str
    author_type: str
    created_at: str

    model_config = {"from_attributes": True}
