from typing import Optional

from sqlmodel import Field, SQLModel


class Workspace(SQLModel, table=True):
    __tablename__ = "workspace"

    id: str = Field(primary_key=True)
    name: str = Field(max_length=200)
    slug: str = Field(unique=True, index=True, max_length=60)
    description: Optional[str] = None
    default_project_root: Optional[str] = None
    settings_json: Optional[str] = None
    created_at: str
    updated_at: str
