from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import REF_ENTITY_TYPES
from app.core.uri_policy import MAX_LINK_LENGTH, normalize_link

_ENTITY_TYPES = frozenset(REF_ENTITY_TYPES)


class LinkCreate(BaseModel):
    entity_type: str
    entity_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=MAX_LINK_LENGTH)
    title: Optional[str] = Field(default=None, max_length=300)

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in _ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of: {', '.join(sorted(_ENTITY_TYPES))}"
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """#118: one shared policy, not a prefix check.

        This used to block three literal prefixes and let everything else
        through — `file:`, custom protocols, and any of the encodings that make
        `javascript:` not start with `javascript:`. A `Link` row is an absolute
        bookmark, so relative references are not accepted here either.
        """
        return normalize_link(v, label="url", allow_relative=False)


class LinkRead(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    url: str
    title: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}
