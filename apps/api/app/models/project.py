from typing import Optional

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.core.constants import project_status_check_sql


class Project(SQLModel, table=True):
    __tablename__ = "project"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_project_workspace_slug"),
        CheckConstraint(project_status_check_sql(), name="ck_project_status"),
    )

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    title: str = Field(max_length=200)
    slug: str = Field(max_length=60)
    summary: Optional[str] = None
    project_type: Optional[str] = None
    status: str = Field(default="idea")
    priority: Optional[str] = None
    folder_path: Optional[str] = None
    created_at: str
    updated_at: str
    archived_at: Optional[str] = None
