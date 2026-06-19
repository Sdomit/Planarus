import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=60)
    description: Optional[str] = None
    default_project_root: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters, numbers, and hyphens; "
                "cannot start or end with a hyphen"
            )
        return v


class WorkspaceRead(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    default_project_root: Optional[str]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
