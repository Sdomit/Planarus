from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class SyncBaseline(SQLModel, table=True):
    """The last-synced manifest for a project (Phase 10.6b).

    After a successful sync both replicas agree; that agreed manifest is stored
    here as the ``base`` for the next three-way diff, so future syncs can tell a
    one-sided change from a genuine conflict. One row per project.
    """

    __tablename__ = "syncbaseline"
    __table_args__ = (Index("ix_syncbaseline_project_id", "project_id", unique=True),)

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id")
    manifest_json: str
    updated_at: str
