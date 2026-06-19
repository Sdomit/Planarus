from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db.session import get_session
from app.schemas.workspace import WorkspaceCreate, WorkspaceRead
from app.services import workspace_service

router = APIRouter()


@router.get("/workspaces", response_model=list[WorkspaceRead])
def list_workspaces(session: Session = Depends(get_session)) -> list[WorkspaceRead]:
    return workspace_service.list_workspaces(session)


@router.post(
    "/workspaces",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(
    data: WorkspaceCreate,
    session: Session = Depends(get_session),
) -> WorkspaceRead:
    return workspace_service.create_workspace(session, data)
