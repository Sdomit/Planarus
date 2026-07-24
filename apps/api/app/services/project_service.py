import json
import logging
import os
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.core.config import settings
from app.core.exceptions import ConflictError, PolicyError
from app.core.utils import new_id, now_utc
from app.fsmemory.path_safety import PathSafetyError
from app.fsmemory.project_root import (
    ProjectRootError,
    managed_root_for,
    roots_overlap,
    validate_local_root,
)
from app.models.blocker import Blocker
from app.models.checklist_item import ChecklistItem
from app.models.comment import Comment
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.link import Link
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.project import Project
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.task import Task
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services import context_service
from app.services.audit_service import create_audit_event

logger = logging.getLogger(__name__)


def _provision_on_save(session: Session, project: Project) -> None:
    """Auto-provision the project folder + context pack after a save.

    DB is authoritative and already committed before this runs. Both
    PathSafetyError and OSError are caught here and made non-fatal: the
    in-progress regeneration session is rolled back, the failure is recorded as
    a context_regen AuditEvent, a warning is logged, and the already-committed
    project is still returned to the caller. No exception propagates.
    """
    if not project.folder_path:
        return
    try:
        context_service.provision_and_regenerate(session, project, actor_type="human")
    except (PathSafetyError, OSError) as exc:
        session.rollback()
        create_audit_event(
            session,
            event_type="context_regen",
            actor_type="system",
            entity_type="project",
            entity_id=project.id,
            workspace_id=project.workspace_id,
            project_id=project.id,
            payload_json=json.dumps({"status": "error", "error": str(exc)}),
        )
        session.commit()
        logger.warning("context provisioning failed for %s: %s", project.id, exc)


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


def _assert_no_overlap(session: Session, self_id: str, root_real: str) -> None:
    """Reject a local root that equals/contains/is-contained-by another project's
    root (#115). Cross-workspace: two projects must never share a directory."""
    others = session.exec(
        select(Project).where(
            Project.id != self_id, Project.folder_path.is_not(None)
        )
    ).all()
    for other in others:
        if roots_overlap(root_real, os.path.realpath(other.folder_path)):
            raise ConflictError(
                "folder_path overlaps another project's root; "
                "choose a separate directory"
            )


def _validated_local_folder(
    session: Session, self_id: str, requested: Optional[str]
) -> Optional[str]:
    """Local escape hatch: canonicalise + vet an operator-supplied root, or None."""
    if not requested:
        return None
    try:
        root = validate_local_root(requested)
    except (PathSafetyError, ProjectRootError) as exc:
        raise PolicyError(f"invalid folder_path: {exc}") from exc
    _assert_no_overlap(session, self_id, root)
    return root


def _folder_for_create(
    session: Session, workspace_id: str, project_id: str, requested: Optional[str]
) -> Optional[str]:
    """Resolve the on-disk root for a new project (#115).

    Auth-enabled mode: server-owned, derived from ids — any tenant-supplied path
    is ignored. Local mode: the vetted escape-hatch path (or None = folderless).
    """
    if settings.auth_enabled:
        return managed_root_for(workspace_id, project_id)
    return _validated_local_folder(session, project_id, requested)


def create_project(session: Session, data: ProjectCreate) -> Project:
    now = now_utc()
    project_id = new_id("proj")
    folder_path = _folder_for_create(
        session, data.workspace_id, project_id, data.folder_path
    )
    project = Project(
        id=project_id,
        workspace_id=data.workspace_id,
        title=data.title,
        slug=data.slug,
        summary=data.summary,
        status=data.status,
        folder_path=folder_path,
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
    _provision_on_save(session, project)
    session.refresh(project)
    return project


def update_project(
    session: Session, project_id: str, data: ProjectUpdate
) -> Optional[Project]:
    project = session.get(Project, project_id)
    if project is None:
        return None

    update_data = data.model_dump(exclude_unset=True)
    # folder_path is handled out of band and kept out of the audit payload — it
    # is server-managed in auth mode, and we never log absolute host paths (#115).
    folder_in_patch = "folder_path" in update_data
    requested_folder = update_data.pop("folder_path", None)
    now = now_utc()
    for key, value in update_data.items():
        setattr(project, key, value)
    if folder_in_patch and not settings.auth_enabled:
        # Local escape hatch may repoint or clear the root; auth mode ignores the
        # client value entirely (the root is fixed by ids).
        project.folder_path = _validated_local_folder(
            session, project.id, requested_folder
        )
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
    _provision_on_save(session, project)
    session.refresh(project)
    return project


def set_archived(
    session: Session, project_id: str, archived: bool
) -> Optional[Project]:
    """Soft archive/unarchive. Archiving stamps ``archived_at`` and forces
    ``status='archived'``; unarchiving clears the stamp and, since no prior
    status is remembered, lands the project on ``'active'``.

    ponytail: no prior-status memory on unarchive — 'active' is the sane default,
    add a status snapshot only if users ask to restore the exact prior status.
    """
    project = session.get(Project, project_id)
    if project is None:
        return None
    now = now_utc()
    if archived:
        project.archived_at = now
        project.status = "archived"
    else:
        project.archived_at = None
        if project.status == "archived":
            project.status = "active"
    project.updated_at = now
    session.add(project)
    create_audit_event(
        session,
        event_type="archive" if archived else "unarchive",
        actor_type="human",
        entity_type="project",
        entity_id=project_id,
        workspace_id=project.workspace_id,
        project_id=project_id,
    )
    session.commit()
    session.refresh(project)
    return project


def _unique_slug(session: Session, workspace_id: str, base: str) -> str:
    """First free ``base-copy`` / ``base-copy-N`` slug in the workspace."""
    candidate = f"{base}-copy"
    n = 1
    while (
        session.exec(
            select(Project.id).where(
                Project.workspace_id == workspace_id, Project.slug == candidate
            )
        ).first()
        is not None
    ):
        n += 1
        candidate = f"{base}-copy-{n}"
    return candidate[:60]


def duplicate_project(session: Session, project_id: str) -> Optional[Project]:
    """Deep-copy a project and its *planning* graph into a new project.

    Copied: phases, stages, tasks (+ checklist items), decisions, risks,
    blockers, milestones, docs, and their comments/links — with every internal
    id remapped. Deliberately NOT copied (ponytail: they belong to the original,
    not a fresh clone): audit history, approval requests, email logs, context
    files, notification rules, agent runs. The copy starts folderless and at
    status 'idea'.
    """
    src = session.get(Project, project_id)
    if src is None:
        return None
    now = now_utc()
    new_proj = Project(
        id=new_id("proj"),
        workspace_id=src.workspace_id,
        title=f"{src.title} (copy)",
        slug=_unique_slug(session, src.workspace_id, src.slug),
        summary=src.summary,
        project_type=src.project_type,
        status="idea",
        priority=src.priority,
        folder_path=None,  # ponytail: folderless copy → no re-provision / disk collision
        created_at=now,
        updated_at=now,
    )
    session.add(new_proj)
    session.flush()

    # entity_type -> {old_id: new_id}; seeds the polymorphic comment/link remap.
    idmap: dict[str, dict[str, str]] = {"project": {project_id: new_proj.id}}

    def clone(model, entity_type: str, fk_remap: dict[str, str]) -> None:
        rows = session.exec(select(model).where(model.project_id == project_id)).all()
        m: dict[str, str] = {}
        for row in rows:
            data = row.model_dump()
            old = data["id"]
            data["id"] = new_id(old.split("_", 1)[0])
            data["project_id"] = new_proj.id
            for field, src_type in fk_remap.items():
                cur = data.get(field)
                if cur is not None:
                    data[field] = idmap.get(src_type, {}).get(cur, cur)
            if "created_at" in data:
                data["created_at"] = now
            if "updated_at" in data:
                data["updated_at"] = now
            session.add(model(**data))
            m[old] = data["id"]
        session.flush()
        idmap[entity_type] = m

    clone(Phase, "phase", {})
    clone(Stage, "stage", {"phase_id": "phase"})
    clone(Task, "task", {"phase_id": "phase", "stage_id": "stage"})

    # Checklist items carry no project_id — copy via their parent tasks.
    task_map = idmap["task"]
    if task_map:
        for row in session.exec(
            select(ChecklistItem).where(ChecklistItem.task_id.in_(list(task_map.keys())))
        ).all():
            data = row.model_dump()
            data["id"] = new_id(data["id"].split("_", 1)[0])
            data["task_id"] = task_map[data["task_id"]]
            data["created_at"] = now
            data["updated_at"] = now
            session.add(ChecklistItem(**data))
        session.flush()

    clone(Decision, "decision", {"phase_id": "phase"})
    clone(Risk, "risk", {"phase_id": "phase"})
    clone(Blocker, "blocker", {"task_id": "task"})
    clone(Milestone, "milestone", {"phase_id": "phase"})

    # Docs: self-referential parent_doc_id → two-pass so a parent needn't precede
    # its child. Export refs are folder-bound, so they're dropped on the copy.
    docmap: dict[str, str] = {}
    doc_parents: dict[str, Optional[str]] = {}
    for row in session.exec(select(Doc).where(Doc.project_id == project_id)).all():
        data = row.model_dump()
        old = data["id"]
        new = new_id("doc")
        doc_parents[new] = data.get("parent_doc_id")
        data.update(
            id=new,
            project_id=new_proj.id,
            parent_doc_id=None,
            export_relative_path=None,
            export_checksum=None,
            exported_at=None,
            created_at=now,
            updated_at=now,
        )
        session.add(Doc(**data))
        docmap[old] = new
    session.flush()
    idmap["doc"] = docmap
    for new_doc_id, old_parent in doc_parents.items():
        if old_parent is not None:
            child = session.get(Doc, new_doc_id)
            child.parent_doc_id = docmap.get(old_parent)
            session.add(child)
    session.flush()

    # Comments/links: entity_id is polymorphic — remap through idmap[entity_type].
    for model in (Comment, Link):
        for row in session.exec(
            select(model).where(model.project_id == project_id)
        ).all():
            data = row.model_dump()
            data["id"] = new_id(data["id"].split("_", 1)[0])
            data["project_id"] = new_proj.id
            eid = data["entity_id"]
            data["entity_id"] = idmap.get(data["entity_type"], {}).get(eid, eid)
            data["created_at"] = now
            session.add(model(**data))
    session.flush()

    create_audit_event(
        session,
        event_type="duplicate",
        actor_type="human",
        entity_type="project",
        entity_id=new_proj.id,
        workspace_id=new_proj.workspace_id,
        project_id=new_proj.id,
        payload_json=json.dumps({"source_project_id": project_id}),
    )
    session.commit()
    session.refresh(new_proj)
    return new_proj


def purge_project(session: Session, project_id: str) -> bool:
    """Permanently delete an *archived* project and every project-scoped row.

    Guarded: the project must already be archived (409 otherwise) so a hard
    delete is always a two-step, deliberate act. Children are removed FK-safe
    (reversed topological order); a workspace-scoped audit trace survives.

    ponytail: purges DB rows only — on-disk context files under folder_path are
    left for the OS/user; wire in fsmemory cleanup if orphaned files bite.
    """
    proj = session.get(Project, project_id)
    if proj is None:
        return False
    if proj.archived_at is None:
        raise ConflictError(
            "project must be archived before it can be permanently deleted"
        )
    # project_id left NULL so this trace is not swept by the cascade below.
    create_audit_event(
        session,
        event_type="delete",
        actor_type="human",
        entity_type="project",
        entity_id=project_id,
        workspace_id=proj.workspace_id,
    )
    task_ids = select(Task.id).where(Task.project_id == project_id)
    session.execute(sa_delete(ChecklistItem).where(ChecklistItem.task_id.in_(task_ids)))
    for table in reversed(SQLModel.metadata.sorted_tables):
        if "project_id" in table.columns:
            session.execute(sa_delete(table).where(table.c.project_id == project_id))
    session.delete(proj)
    session.commit()
    return True
