from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.git import GitRepoLink
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
