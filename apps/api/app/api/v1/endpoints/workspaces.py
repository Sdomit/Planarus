from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.core import tenant
from app.core.tenant import tenant_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.workspace import WorkspaceCreate, WorkspaceRead
from app.services import auth_service, workspace_service

router = APIRouter()


@router.get("/workspaces", response_model=list[WorkspaceRead])
def list_workspaces(
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> list[WorkspaceRead]:
    workspaces = workspace_service.list_workspaces(session)
    if user is not None:  # auth enabled → only the caller's workspaces
        allowed = tenant.user_workspace_ids(session, user)
        workspaces = [w for w in workspaces if w.id in allowed]
    return workspaces


@router.post(
    "/workspaces",
    response_model=WorkspaceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_workspace(
    data: WorkspaceCreate,
    session: Session = Depends(get_session),
    user: Optional[User] = Depends(tenant_user),
) -> WorkspaceRead:
    workspace = workspace_service.create_workspace(session, data)
    # Auth enabled → the creator becomes the workspace owner, so they can see and
    # manage what they just made (no bootstrap step needed in hosted mode).
    if user is not None:
        auth_service.add_member(session, workspace.id, user.id, "owner")
    return workspace
