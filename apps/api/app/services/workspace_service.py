from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.errors import ConflictError
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
    try:
        # Flush the parent first so the audit row's FK target exists (FKs are
        # enforced) and a duplicate-slug violation surfaces here, not mid-audit.
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        # Broad IntegrityError→409 is Phase 2-safe because Pydantic validates the
        # slug format and the only realistic violation is the unique-slug constraint.
        # Narrow to a dialect-aware constraint-name check before external write surfaces.
        raise ConflictError(f"workspace slug '{data.slug}' already exists") from exc
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
