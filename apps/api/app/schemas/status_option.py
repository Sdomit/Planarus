import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import STATUS_OPTION_ENTITY_TYPES

_ENTITY_TYPES = frozenset(STATUS_OPTION_ENTITY_TYPES)
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _validate_color(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not _HEX_COLOR.match(v):
        raise ValueError("color must be a hex value like #8b5cf6")
    return v.lower()


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

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_color(v)


class StatusOptionUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=60)
    color: Optional[str] = None

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        return _validate_color(v)


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
