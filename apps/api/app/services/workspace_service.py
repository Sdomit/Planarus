from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceCreate
from app.services.audit_service import create_audit_event


def list_workspaces(session: Session) -> list[Workspace]:
    return list(session.exec(select(Workspace)).all())


def create_workspace(session: Session, data: WorkspaceCreate) -> Workspace:
    now = now_utc()
    workspace = Workspace(
        id=new_id("ws"),
        name=data.name,
        slug=data.slug,
        description=data.description,
        default_project_root=data.default_project_root,
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="workspace",
        entity_id=workspace.id,
        workspace_id=workspace.id,
    )
    session.commit()
    session.refresh(workspace)
    return workspace
