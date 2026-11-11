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
    # Capability mode is deliberately separate from project_type: a project can
    # be an "app" (type) while still being a normal, non-agentic project.
    mode: str = Field(default="agentic", max_length=16, index=True)
    status: str = Field(default="idea", index=True)
    priority: Optional[str] = None
    folder_path: Optional[str] = None
    created_at: str
    updated_at: str
    archived_at: Optional[str] = None
