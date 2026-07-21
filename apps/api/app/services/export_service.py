"""Project export / import — round-trippable JSON (Phase 17.6).

Serializes a project's *planning* graph (the same set
``project_service.duplicate_project`` copies): phases, stages, tasks (+ checklist
items), decisions, risks, blockers, milestones, docs, and their comments/links.
Deliberately excluded (they belong to the source instance, not a portable copy):
audit history, approvals, email logs, context files, notification rules, agent
runs, and webhook subscriptions.

Export keeps original ids so relationships survive the JSON. Import remaps every
id into a fresh project and NULLs cross-instance attribution FKs (assignee /
author / updated_by) — the referenced users won't exist on the target.
"""
from __future__ import annotations

from typing import Optional

from sqlmodel import Session, select

from app.core.utils import new_id, now_utc
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
from app.services.audit_service import create_audit_event
from app.services.project_service import _unique_slug

EXPORT_VERSION = 1

# (json key, model) — project-scoped entities, exported/imported directly.
_PROJECT_SCOPED = [
    ("phases", Phase),
    ("stages", Stage),
    ("tasks", Task),
    ("decisions", Decision),
    ("risks", Risk),
    ("blockers", Blocker),
    ("milestones", Milestone),
    ("docs", Doc),
    ("comments", Comment),
    ("links", Link),
]


def export_project(session: Session, project_id: str) -> Optional[dict]:
    """Serialize a project + its planning graph to a JSON-safe dict (original ids)."""
    proj = session.get(Project, project_id)
    if proj is None:
        return None
    out: dict = {"planarus_export": EXPORT_VERSION, "project": proj.model_dump()}
    for key, model in _PROJECT_SCOPED:
        rows = session.exec(select(model).where(model.project_id == project_id)).all()
        out[key] = [r.model_dump() for r in rows]
    task_ids = [t["id"] for t in out["tasks"]]
    out["checklist_items"] = (
        [
            r.model_dump()
            for r in session.exec(
                select(ChecklistItem).where(ChecklistItem.task_id.in_(task_ids))
            ).all()
        ]
        if task_ids
        else []
    )
    return out


def import_project(session: Session, workspace_id: str, data: dict) -> Project:
    """Create a fresh project from an export dict, remapping every id. Raises
    ValueError on an unrecognized payload."""
    if not isinstance(data, dict) or data.get("planarus_export") != EXPORT_VERSION:
        raise ValueError("unrecognized export format")
    src = data.get("project") or {}
    now = now_utc()
    new_proj = Project(
        id=new_id("proj"),
        workspace_id=workspace_id,
        title=str(src.get("title") or "Imported project")[:200],
        slug=_unique_slug(session, workspace_id, str(src.get("slug") or "imported")),
        summary=src.get("summary"),
        project_type=src.get("project_type"),
        status="idea",
        priority=src.get("priority"),
        folder_path=None,
        created_at=now,
        updated_at=now,
    )
    session.add(new_proj)
    session.flush()

    idmap: dict[str, dict[str, str]] = {"project": {src.get("id"): new_proj.id}}

    def load(key: str, model, entity_type: str, fk_remap: dict, drop: tuple = ()) -> None:
        m: dict[str, str] = {}
        for row in data.get(key, []):
            d = dict(row)
            old = d["id"]
            d["id"] = new_id(old.split("_", 1)[0])
            d["project_id"] = new_proj.id
            for field, src_type in fk_remap.items():
                if d.get(field) is not None:
                    d[field] = idmap.get(src_type, {}).get(d[field], d[field])
            for field in drop:  # cross-instance attribution FKs won't resolve here
                d[field] = None
            for ts in ("created_at", "updated_at"):
                if ts in d:
                    d[ts] = now
            session.add(model(**d))
            m[old] = d["id"]
        session.flush()
        idmap[entity_type] = m

    load("phases", Phase, "phase", {})
    load("stages", Stage, "stage", {"phase_id": "phase"})
    load("tasks", Task, "task", {"phase_id": "phase", "stage_id": "stage"}, drop=("assignee_id",))

    task_map = idmap["task"]
    for row in data.get("checklist_items", []):
        d = dict(row)
        if d.get("task_id") not in task_map:
            continue  # orphan (parent task missing) → skip
        d["id"] = new_id(d["id"].split("_", 1)[0])
        d["task_id"] = task_map[d["task_id"]]
        for ts in ("created_at", "updated_at"):
            if ts in d:
                d[ts] = now
        session.add(ChecklistItem(**d))
    session.flush()

    load("decisions", Decision, "decision", {})
    load("risks", Risk, "risk", {})
    load("blockers", Blocker, "blocker", {"task_id": "task"})
    load("milestones", Milestone, "milestone", {"phase_id": "phase"})

    # Docs: self-referential parent → two-pass (a parent needn't precede its child).
    docmap: dict[str, str] = {}
    doc_parents: dict[str, Optional[str]] = {}
    for row in data.get("docs", []):
        d = dict(row)
        old, new = d["id"], new_id("doc")
        doc_parents[new] = d.get("parent_doc_id")
        d.update(
            id=new, project_id=new_proj.id, parent_doc_id=None,
            export_relative_path=None, export_checksum=None, exported_at=None,
            updated_by=None, created_at=now, updated_at=now,
        )
        session.add(Doc(**d))
        docmap[old] = new
    session.flush()
    idmap["doc"] = docmap
    for new_doc_id, old_parent in doc_parents.items():
        if old_parent is not None and old_parent in docmap:
            child = session.get(Doc, new_doc_id)
            child.parent_doc_id = docmap[old_parent]
            session.add(child)
    session.flush()

    # Comments/links: entity_id is polymorphic — remap through idmap[entity_type].
    for key, model, drop in (("comments", Comment, ("author_id",)), ("links", Link, ())):
        for row in data.get(key, []):
            d = dict(row)
            d["id"] = new_id(d["id"].split("_", 1)[0])
            d["project_id"] = new_proj.id
            eid = d.get("entity_id")
            d["entity_id"] = idmap.get(d.get("entity_type"), {}).get(eid, eid)
            for field in drop:
                d[field] = None
            if "created_at" in d:
                d["created_at"] = now
            session.add(model(**d))
    session.flush()

    create_audit_event(
        session, event_type="import", actor_type="user", entity_type="project",
        entity_id=new_proj.id, workspace_id=workspace_id, project_id=new_proj.id,
    )
    session.commit()
    session.refresh(new_proj)
    return new_proj
