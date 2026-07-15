from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlmodel import Session

from app.db.session import get_session
from app.models.workspace import Workspace
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter()


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(
    workspace_id: str | None = None,
    include_archived: bool = False,
    session: Session = Depends(get_session),
) -> list[ProjectRead]:
    return project_service.list_projects(
        session, workspace_id=workspace_id, include_archived=include_archived
    )


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    if session.get(Workspace, data.workspace_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{data.workspace_id}' not found",
        )
    return project_service.create_project(session, data)


@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = project_service.get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.patch("/projects/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = project_service.update_project(session, project_id, data)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = project_service.set_archived(session, project_id, True)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post("/projects/{project_id}/unarchive", response_model=ProjectRead)
def unarchive_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = project_service.set_archived(session, project_id, False)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post(
    "/projects/{project_id}/duplicate",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def duplicate_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = project_service.duplicate_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    session: Session = Depends(get_session),
) -> Response:
    # Permanent purge; must already be archived (service raises ConflictError → 409).
    if not project_service.purge_project(session, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
