from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import STATUS_OPTION_ENTITY_TYPES

_ENTITY_TYPES = frozenset(STATUS_OPTION_ENTITY_TYPES)


class StatusOptionCreate(BaseModel):
    entity_type: str
    label: str = Field(min_length=1, max_length=60)
    color: Optional[str] = None

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v: str) -> str:
        if v not in _ENTITY_TYPES:
            raise ValueError(
                f"entity_type must be one of: {', '.join(sorted(_ENTITY_TYPES))}"
            )
        return v


class StatusOptionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    color: Optional[str] = None


class StatusOptionRead(BaseModel):
    """A status a card can take. `builtin` options are the canonical ones (no
    stored row, `id` is null and they can't be edited/deleted); the rest are the
    project's custom options."""

    id: Optional[str]
    key: str
    label: str
    color: Optional[str]
    sort_order: int
    builtin: bool
