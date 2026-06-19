import json
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.errors import ConflictError
from app.core.utils import new_id, now_utc
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.audit_service import create_audit_event


def get_project(session: Session, project_id: str) -> Optional[Project]:
    return session.get(Project, project_id)


def list_projects(
    session: Session,
    workspace_id: Optional[str] = None,
    include_archived: bool = False,
) -> list[Project]:
    stmt = select(Project)
    if not include_archived:
        stmt = stmt.where(Project.archived_at == None)  # noqa: E711
    if workspace_id:
        stmt = stmt.where(Project.workspace_id == workspace_id)
    return list(session.exec(stmt).all())


def create_project(session: Session, data: ProjectCreate) -> Project:
    now = now_utc()
    project = Project(
        id=new_id("proj"),
        workspace_id=data.workspace_id,
        title=data.title,
        slug=data.slug,
        summary=data.summary,
        status=data.status,
        folder_path=data.folder_path,
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    try:
        # Flush the parent first so the audit row's FK target exists (FKs are
        # enforced) and a duplicate-slug violation surfaces here, not mid-audit.
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        # Broad IntegrityError→409 is Phase 2-safe because the route prevalidates
        # workspace FK existence and Pydantic validates status; the only realistic
        # violation here is the duplicate-slug UniqueConstraint. Narrow this to a
        # dialect-aware constraint-name check before opening external write surfaces.
        raise ConflictError(
            f"project slug '{data.slug}' already exists in this workspace"
        ) from exc
    create_audit_event(
        session,
        event_type="create",
        actor_type="human",
        entity_type="project",
        entity_id=project.id,
        workspace_id=data.workspace_id,
        project_id=project.id,
    )
    session.commit()
    session.refresh(project)
    return project


def update_project(
    session: Session, project_id: str, data: ProjectUpdate
) -> Optional[Project]:
    project = session.get(Project, project_id)
    if project is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    now = now_utc()
    for key, value in update_data.items():
        setattr(project, key, value)
    project.updated_at = now
    session.add(project)

    create_audit_event(
        session,
        event_type="update",
        actor_type="human",
        entity_type="project",
        entity_id=project_id,
        workspace_id=project.workspace_id,
        project_id=project_id,
        payload_json=json.dumps(update_data),
    )
    session.commit()
    session.refresh(project)
    return project
