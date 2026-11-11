"""Short-lived MCP activity markers used by the shell indicator."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.mcp_activity import McpActivity
from app.models.project import Project
from app.schemas.mcp_activity import McpActivityRead

ACTIVE_WINDOW_SECONDS = 60


def touch(session: Session, actor_ref: str, project_id: str, tool_name: str) -> None:
    """Record a scoped MCP tool call without retaining its arguments or output."""
    activity = session.exec(
        select(McpActivity).where(
            McpActivity.actor_ref == actor_ref,
            McpActivity.project_id == project_id,
        )
    ).first()
    if activity is None:
        activity = McpActivity(
            id=new_id("mca"),
            actor_ref=actor_ref,
            project_id=project_id,
            tool_name=tool_name,
            last_seen_at=now_utc(),
        )
    else:
        activity.tool_name = tool_name
        activity.last_seen_at = now_utc()
    session.add(activity)
    session.commit()


def active(session: Session, workspace_ids: set[str] | None = None) -> list[McpActivityRead]:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ACTIVE_WINDOW_SECONDS)).isoformat()
    rows = session.exec(
        select(McpActivity, Project)
        .join(Project, McpActivity.project_id == Project.id)
        .where(
            McpActivity.last_seen_at >= cutoff,
            or_(Project.mode.is_(None), Project.mode == "agentic"),
        )
        .order_by(McpActivity.last_seen_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [
        McpActivityRead(
            actor_ref=activity.actor_ref,
            project_id=project.id,
            project_title=project.title,
            tool_name=activity.tool_name,
            last_seen_at=activity.last_seen_at,
        )
        for activity, project in rows
        if workspace_ids is None or project.workspace_id in workspace_ids
    ]
