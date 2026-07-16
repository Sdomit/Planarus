from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core import tenant
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter()


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    workspace_id: str | None = None,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[ProjectRead]:
    projects = project_service.list_projects(session, workspace_id=workspace_id)
    if user is not None:  # auth enabled → scope to the caller's workspaces
        allowed = tenant.user_workspace_ids(session, user)
        projects = [p for p in projects if p.workspace_id in allowed]
    return projects


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ProjectRead:
    if session.get(Workspace, data.workspace_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{data.workspace_id}' not found",
        )
    tenant.require_workspace_access(
        session, data.workspace_id, user, *tenant.WRITE_ROLES
    )
    return project_service.create_project(session, data)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ProjectRead:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    tenant.require_project_access(session, project, user, *tenant.READ_ROLES)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> ProjectRead:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    tenant.require_project_access(session, project, user, *tenant.WRITE_ROLES)
    updated = project_service.update_project(session, project_id, data)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return updated
