"""Recent, project-scoped MCP activity for the local control-plane UI."""
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class McpActivity(SQLModel, table=True):
    """One recent tool-use marker per MCP client and project.

    This is intentionally not an execution log. A stdio MCP process is launched
    on demand and may finish a tool call in milliseconds, so ``last_seen_at`` is
    a small, honest recency window for the UI rather than a claim of a persistent
    network connection.
    """

    __tablename__ = "mcp_activity"
    __table_args__ = (
        UniqueConstraint("actor_ref", "project_id", name="uq_mcp_activity_actor_project"),
        Index("ix_mcp_activity_last_seen", "last_seen_at"),
    )

    id: str = Field(primary_key=True)
    actor_ref: str = Field(max_length=160)
    project_id: str = Field(foreign_key="project.id", index=True)
    tool_name: str = Field(max_length=120)
    last_seen_at: str
