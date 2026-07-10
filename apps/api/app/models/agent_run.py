from typing import Optional

from sqlalchemy import CheckConstraint, Index
from sqlmodel import Field, SQLModel

from app.core.constants import (
    agent_family_check_sql,
    agent_run_mode_check_sql,
    agent_run_status_check_sql,
)


class AgentRun(SQLModel, table=True):
    """Immutable-ish execution log entry: one row per agent invocation (Phase 9).

    Manually entered by the local human (no agent writes here — external AI
    surfaces never touch this table). Analytics are derived, never stored.
    """

    __tablename__ = "agentrun"
    __table_args__ = (
        CheckConstraint(agent_family_check_sql(), name="ck_agentrun_family"),
        CheckConstraint(agent_run_mode_check_sql(), name="ck_agentrun_mode"),
        CheckConstraint(agent_run_status_check_sql(), name="ck_agentrun_status"),
        Index("ix_agentrun_project_started", "project_id", "started_at"),
    )

    id: str = Field(primary_key=True)
    project_id: str = Field(foreign_key="project.id", index=True)
    agent_family: str = Field(default="unspecified")
    agent_name: Optional[str] = Field(default=None, max_length=120)
    mode: Optional[str] = None
    status: str = Field(default="started")
    summary: Optional[str] = None
    started_at: str
    ended_at: Optional[str] = None
    created_at: str
    updated_at: str
