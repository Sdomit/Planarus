"""One capability boundary for agent-only project features."""

from fastapi import HTTPException, status
from sqlmodel import Session

from app.models.project import Project


def is_agentic(project: Project) -> bool:
    # Databases are backfilled by migration 0037. Treat an absent value as
    # Agentic during rollout so existing projects are never locked out before
    # that migration has run.
    return project.mode != "normal"


def require_agentic(project: Project) -> Project:
    """Reject before an agent-only handler reads or changes project data."""
    if not is_agentic(project):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent features are disabled for this Normal project",
        )
    return project


def get_agentic_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return require_agentic(project)
