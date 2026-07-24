from typing import Optional

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class AuditEvent(SQLModel, table=True):
    __tablename__ = "auditevent"
    # Composite index authored by migration 0001; declared here so autogenerate
    # does not mark it for removal. Load-bearing: the proposal audit trail reads
    # filter (entity_type, entity_id) — see approval_service.get_proposal_audit.
    __table_args__ = (Index("ix_auditevent_entity", "entity_type", "entity_id"),)

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
