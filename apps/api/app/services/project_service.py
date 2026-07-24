import json
import logging
from typing import Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc
from app.fsmemory.path_safety import PathSafetyError
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

    # parent_task_id is a self-reference, so `clone` can't remap it in one pass:
    # a child may be cloned before its parent, and idmap["task"] only exists once
    # the loop finishes. Same two-pass shape as docs below. Left unremapped, the
    # copy's sub-tasks point at the ORIGINAL project's parent tasks — a silent
    # cross-project FK that later 500s an export/import round-trip (#87).
    task_map = idmap["task"]
    for src_task in session.exec(
        select(Task).where(Task.project_id == project_id, Task.parent_task_id.is_not(None))
    ).all():
        new_child = session.get(Task, task_map[src_task.id])
        new_child.parent_task_id = task_map.get(src_task.parent_task_id)
        session.add(new_child)
    session.flush()

    # Checklist items carry no project_id — copy via their parent tasks.
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
