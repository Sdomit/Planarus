from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.git import GitRepoLink, GitSnapshot
from app.services import git_service, project_service

router = APIRouter()


@router.get("/projects/{project_id}/git", response_model=GitRepoLink)
def get_project_git(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitRepoLink:
    """Live read-only Git metadata for the project's folder. Local UI only."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return git_service.collect(project.id, project.folder_path)


@router.get("/projects/{project_id}/git/snapshot", response_model=GitSnapshot)
def get_project_git_snapshot(
    project_id: str,
    session: Session = Depends(get_session),
) -> GitSnapshot:
    """Read-only repo cockpit snapshot (Phase 12a): branches with ahead/behind,
    divergence from the default branch, needs-merge list, working-tree counts,
    and the last-fetch freshness stamp. Local UI only — never mounted on MCP or
    the external API. SHOW, DON'T DO: no mutating path exists."""
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return git_service.snapshot(project.id, project.folder_path)
