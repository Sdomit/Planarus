from typing import Optional

from sqlmodel import Field, SQLModel


class AuditEvent(SQLModel, table=True):
    __tablename__ = "auditevent"

    id: str = Field(primary_key=True)
    workspace_id: Optional[str] = Field(default=None, foreign_key="workspace.id", index=True)
    project_id: Optional[str] = Field(default=None, foreign_key="project.id", index=True)
    actor_type: str
    actor_id: Optional[str] = None
    event_type: str
    entity_type: str
    entity_id: Optional[str] = None
    payload_json: Optional[str] = None
    created_at: str
