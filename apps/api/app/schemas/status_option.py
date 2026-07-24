import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    DEFAULT_STATUS_CATEGORY,
    STATUS_CATEGORIES,
    STATUS_OPTION_ENTITY_TYPES,
)

_ENTITY_TYPES = frozenset(STATUS_OPTION_ENTITY_TYPES)
_CATEGORIES = frozenset(STATUS_CATEGORIES)
_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _validate_category(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if v not in _CATEGORIES:
        raise ValueError(f"category must be one of: {', '.join(sorted(_CATEGORIES))}")
    return v


def _validate_color(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not _HEX_COLOR.match(v):
        raise ValueError("color must be a hex value like #8b5cf6")
    return v.lower()


class StatusOptionCreate(BaseModel):
    entity_type: str
    label: str = Field(min_length=1, max_length=60)
    # #88: what this column means. Omitted → `open`, the pre-#88 behavior.
    category: str = DEFAULT_STATUS_CATEGORY
    color: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        return _validate_category(v)  # type: ignore[return-value]

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
    category: Optional[str] = None
    color: Optional[str] = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        return _validate_category(v)

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
    # open | done | canceled — the built-ins report theirs too, so a client never
    # has to know which keys are special (#88).
    category: str
    color: Optional[str]
    sort_order: int
    builtin: bool
