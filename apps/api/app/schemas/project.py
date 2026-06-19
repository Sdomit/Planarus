import os
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.core.constants import PROJECT_STATUSES

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")

_PROJECT_STATUSES = frozenset(PROJECT_STATUSES)


def _validate_folder_path(v: Optional[str]) -> Optional[str]:
    """A project root, if given, must be a well-formed absolute path.

    Deeper containment safety (symlink/junction/traversal of files *within* the
    root) is enforced by app.fsmemory at write time; this only rejects obviously
    bad roots up front so the common mistake surfaces as a clean 422.
    """
    if v is None or v == "":
        return v
    if "\x00" in v:
        raise ValueError("folder_path must not contain a null byte")
    if not os.path.isabs(v):
        raise ValueError("folder_path must be an absolute path")
    return v


class ProjectCreate(BaseModel):
    workspace_id: str
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=60)
    summary: Optional[str] = None
    status: str = "idea"
    folder_path: Optional[str] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters, numbers, and hyphens; "
                "cannot start or end with a hyphen"
            )
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in _PROJECT_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_PROJECT_STATUSES))}")
        return v

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path(cls, v: Optional[str]) -> Optional[str]:
        return _validate_folder_path(v)


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    summary: Optional[str] = None
    status: Optional[str] = None
    folder_path: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _PROJECT_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_PROJECT_STATUSES))}")
        return v

    @field_validator("folder_path")
    @classmethod
    def validate_folder_path(cls, v: Optional[str]) -> Optional[str]:
        return _validate_folder_path(v)


class ProjectRead(BaseModel):
    id: str
    workspace_id: str
    title: str
    slug: str
    summary: Optional[str]
    project_type: Optional[str]
    status: str
    priority: Optional[str]
    folder_path: Optional[str]
    created_at: str
    updated_at: str
    archived_at: Optional[str]

    model_config = {"from_attributes": True}
