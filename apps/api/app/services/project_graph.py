"""The one description of a project's graph (#87).

Duplicate, export/import and the sync manifest all walk the same set of
project-scoped entities. They used to walk it three separate times, in three
hand-maintained lists, and the code said so out loud::

    # Phase 19: phase_id must be remapped here exactly as milestones do below —
    # this walk is separate from duplicate_project's, so fixing one misses this.

Predictably they drifted. `parent_task_id` was remapped by none of them, so a
duplicated project's sub-tasks pointed at the *original* project's parents — a
silent cross-project reference that later 500s an import. `StatusOption`,
`CalendarEvent` and `Todo` were in no walk at all and in neither "deliberately
excluded" list: silent data loss in an export documented as round-trippable.

So the graph is described once, here, and the three consumers read it:

- ``project_service.duplicate_project`` — copy within one instance
- ``export_service`` — serialize out, and rebuild on another instance
- ``sync.manifest`` — content signatures per entity

Adding an entity is one ``GraphEntity`` row. Leaving one out is now a visible
decision rather than an omission — see ``EXCLUDED`` for what is deliberately not
portable, and ``tests/test_project_graph.py``, which fails when a new
project-scoped table appears in neither list.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlmodel import Session, select

from app.core.utils import new_id
from app.models.blocker import Blocker
from app.models.calendar_event import CalendarEvent
from app.models.checklist_item import ChecklistItem
from app.models.comment import Comment
from app.models.decision import Decision
from app.models.doc import Doc
from app.models.link import Link
from app.models.milestone import Milestone
from app.models.phase import Phase
from app.models.risk import Risk
from app.models.stage import Stage
from app.models.status_option import StatusOption
from app.models.task import Task
from app.models.todo import Todo


@dataclass(frozen=True)
class GraphEntity:
    """One entity kind in a project's portable graph.

    ``key`` is the export JSON key and the ``idmap`` bucket; for polymorphic
    references it is also the value a comment's ``entity_type`` carries.
    """

    key: str
    model: type
    #: the entity's key in an export payload. Plural, and frozen by the v1 format
    #: — renaming one would break every file already written.
    json_key: str = ""
    #: column → the ``key`` of the entity it points at, remapped on copy.
    fk_remap: dict[str, str] = field(default_factory=dict)
    #: column pointing at this same entity kind — needs a second pass, because a
    #: child can be copied before its parent exists in the id map.
    self_ref: Optional[str] = None
    #: (column, parent key) for rows that carry no ``project_id`` and reach the
    #: project only through a parent (checklist items hang off tasks).
    via_parent: Optional[tuple[str, str]] = None
    #: columns blanked on every copy — instance-bound state that must not be
    #: inherited (export bookkeeping, remote sync identifiers).
    reset: tuple[str, ...] = ()
    #: columns blanked only when importing: attribution FKs whose users exist on
    #: the source instance and nowhere else.
    drop_on_import: tuple[str, ...] = ()
    #: rows whose target is (entity_type, entity_id) rather than a typed FK.
    polymorphic: bool = False
    #: columns holding a single hyperlink, checked against the #118 URI policy on
    #: import. Declared here rather than in the importer for the same reason the
    #: FK remaps are: a new entity with a URL column gets the check the day it is
    #: added, instead of the day someone remembers.
    uri_fields: tuple[str, ...] = ()
    #: columns holding a rich-document JSON string whose href/src attributes are
    #: swept by the same policy.
    rich_fields: tuple[str, ...] = ()
    in_duplicate: bool = True
    in_export: bool = True
    in_manifest: bool = True

    @property
    def table(self) -> str:
        return self.model.__tablename__

    @property
    def payload_key(self) -> str:
        return self.json_key or f"{self.key}s"


# Topological order: a parent always precedes anything that points at it, which
# is what makes a single forward pass (plus one self-reference pass) correct.
ENTITIES: tuple[GraphEntity, ...] = (
    GraphEntity("phase", Phase),
    GraphEntity("stage", Stage, fk_remap={"phase_id": "phase"}),
    GraphEntity(
        "task",
        Task,
        fk_remap={"phase_id": "phase", "stage_id": "stage"},
        self_ref="parent_task_id",
        drop_on_import=("assignee_id",),
    ),
    GraphEntity(
        "checklist_item",
        ChecklistItem,
        json_key="checklist_items",
        via_parent=("task_id", "task"),
        # Task-scoped, so the manifest's project_id filter cannot see it; the
        # manifest walks it through its parent tasks instead.
    ),
    GraphEntity("decision", Decision, fk_remap={"phase_id": "phase"}),
    GraphEntity("risk", Risk, fk_remap={"phase_id": "phase"}),
    GraphEntity("blocker", Blocker, fk_remap={"task_id": "task"}),
    GraphEntity("milestone", Milestone, fk_remap={"phase_id": "phase"}),
    # A board's columns travel with it — without them an imported project's cards
    # carry status keys that resolve to nothing.
    GraphEntity("status_option", StatusOption, json_key="status_options"),
    # `external_uid`/`etag` identify the row in a *remote* calendar. A copy has no
    # claim on them; inheriting them would make the next sync fight the original.
    GraphEntity(
        "calendar_event",
        CalendarEvent,
        json_key="calendar_events",
        fk_remap={"phase_id": "phase"},
        reset=("external_uid", "etag"),
    ),
    GraphEntity("todo", Todo, self_ref="parent_id"),
    # Export bookkeeping points at the *source* project's folder.
    GraphEntity(
        "doc",
        Doc,
        self_ref="parent_doc_id",
        reset=("export_relative_path", "export_checksum", "exported_at"),
        drop_on_import=("updated_by",),
        rich_fields=("content_json",),
    ),
    GraphEntity("comment", Comment, polymorphic=True, drop_on_import=("author_id",)),
    GraphEntity("link", Link, polymorphic=True, uri_fields=("url",)),
)

_BY_KEY = {e.key: e for e in ENTITIES}

# Project-scoped tables deliberately left out of the portable graph, with the
# reason. `tests/test_project_graph.py` asserts this list plus ENTITIES covers
# every table that has a project_id, so a new table cannot be silently dropped.
EXCLUDED: dict[str, str] = {
    "auditevent": "history of the source instance, not of the project",
    "approvalrequest": "decisions made on the source instance; a copy re-proposes",
    "emaillog": "delivery record of the source instance",
    "contextfile": "regenerated from the copy's own folder",
    "notificationrule": "addressed to the source instance's recipients",
    "agentrun": "run history of the source instance",
    "calendar_connection": "holds encrypted provider tokens — never copied",
    "oauthtransaction": (
        "a one-time, browser-bound handshake that expires in minutes (#113); it "
        "is meaningless to a copy and carries the initiating user"
    ),
    "syncbaseline": "replica-pair state, meaningless to a copy",
}


def entities_for(surface: str) -> list[GraphEntity]:
    """The graph in walk order for ``duplicate``, ``export`` or ``manifest``."""
    flag = {"duplicate": "in_duplicate", "export": "in_export", "manifest": "in_manifest"}[surface]
    return [e for e in ENTITIES if getattr(e, flag)]


def rows_of(session: Session, entity: GraphEntity, project_id: str, idmap: dict) -> list:
    """Every row of ``entity`` belonging to ``project_id``.

    Rows that carry no ``project_id`` are reached through their parent's ids,
    which the caller has already collected in ``idmap``.
    """
    if entity.via_parent is not None:
        column, parent_key = entity.via_parent
        parent_ids = list(idmap.get(parent_key, {}).keys())
        if not parent_ids:
            return []
        return list(
            session.exec(
                select(entity.model).where(
                    getattr(entity.model, column).in_(parent_ids)
                )
            ).all()
        )
    return list(
        session.exec(
            select(entity.model).where(entity.model.project_id == project_id)
        ).all()
    )


def copy_graph(
    session: Session,
    *,
    surface: str,
    new_project_id: str,
    now: str,
    idmap: dict[str, dict[str, str]],
    rows_for: Callable[[GraphEntity], list[dict]],
) -> None:
    """Copy the whole graph into ``new_project_id``, remapping every reference.

    ``idmap`` maps ``key → {old id: new id}`` and must already hold the project
    itself (so polymorphic references to it resolve). ``rows_for`` yields plain
    dicts — from the database for a duplicate, from the payload for an import —
    which is the only difference between the two callers.

    Unresolvable references are dropped rather than carried over. An id that is
    not in this walk's own map points outside the project being copied: writing
    it through would either dangle (a different instance) or silently attach the
    copy to a foreign project's row (the same one). Every remapped column is
    nullable, so NULL is the honest answer; a polymorphic row whose target
    vanished is skipped entirely, since it has nothing left to be about.
    """
    importing = surface == "import"
    for entity in entities_for("export" if importing else surface):
        pending: list[tuple[str, dict]] = []  # (old id, new row) for the self-ref pass
        mapped: dict[str, str] = {}
        for row in rows_for(entity):
            data = dict(row)
            old = data["id"]
            data["id"] = new_id(old.split("_", 1)[0])
            if entity.via_parent is not None:
                column, parent_key = entity.via_parent
                target = idmap.get(parent_key, {}).get(data.get(column))
                if target is None:
                    continue  # orphan: its parent is not part of this copy
                data[column] = target
            else:
                data["project_id"] = new_project_id
            if entity.polymorphic:
                resolved = idmap.get(data.get("entity_type"), {}).get(data.get("entity_id"))
                if resolved is None:
                    continue
                data["entity_id"] = resolved
            for column, target_key in entity.fk_remap.items():
                if data.get(column) is not None:
                    data[column] = idmap.get(target_key, {}).get(data[column])
            if entity.self_ref is not None:
                data[entity.self_ref] = None  # second pass, once every id is known
            for column in entity.reset:
                data[column] = None
            if importing:
                for column in entity.drop_on_import:
                    data[column] = None
            for stamp in ("created_at", "updated_at"):
                if stamp in data:
                    data[stamp] = now
            session.add(entity.model(**data))
            mapped[old] = data["id"]
            pending.append((old, row))
        session.flush()
        idmap[entity.key] = mapped

        if entity.self_ref is not None:
            for old, original in pending:
                parent = dict(original).get(entity.self_ref)
                if parent is None:
                    continue
                child = session.get(entity.model, mapped[old])
                setattr(child, entity.self_ref, mapped.get(parent))
                session.add(child)
            session.flush()


def manifest_rows(session: Session, project_id: str) -> list[tuple[str, object]]:
    """(entity table, row) for every syncable row of a project, parents first."""
    out: list[tuple[str, object]] = []
    idmap: dict[str, dict[str, str]] = {}
    for entity in entities_for("manifest"):
        rows = rows_of(session, entity, project_id, idmap)
        idmap[entity.key] = {r.id: r.id for r in rows}
        out.extend((entity.table, row) for row in rows)
    return out


def entity_by_key(key: str) -> Optional[GraphEntity]:
    return _BY_KEY.get(key)
