from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import REF_ENTITY_TYPES

_ENTITY_TYPES = frozenset(REF_ENTITY_TYPES)


class LinkCreate(BaseModel):
    entity_type: str
    entity_id: str = Field(min_length=1)
    url: str = Field(min_length=1, max_length=2000)
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
        # ponytail: shape check only, not a full URL parser. Blocks the obvious
        # javascript:/data: injection vectors; http(s)/file/agentboard pass.
        lowered = v.strip().lower()
        if lowered.startswith(("javascript:", "data:", "vbscript:")):
            raise ValueError("url scheme is not allowed")
        return v.strip()


class LinkRead(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    url: str
    title: Optional[str]
    created_at: str

    model_config = {"from_attributes": True}
