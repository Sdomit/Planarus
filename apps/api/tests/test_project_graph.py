"""#87 — one graph description, and the four bugs its absence caused.

Duplicate, export/import and the sync manifest walked the same graph from three
hand-maintained lists. They drifted: `parent_task_id` was remapped by none of
them, and `StatusOption` / `CalendarEvent` / `Todo` were in no list at all — data
loss in an export documented as round-trippable, and cross-project references in
a copy that later 500 an import.

The first test is the one that keeps this closed: a new project-scoped table must
be declared as travelling or as deliberately excluded, or it fails here.
"""
import pytest
from sqlmodel import Session, SQLModel, select

import app.models  # noqa: F401 — registers every table in SQLModel.metadata
from app.core.utils import new_id, now_utc
from app.models.calendar_connection import CalendarConnection
from app.models.calendar_event import CalendarEvent
from app.models.status_option import StatusOption
from app.models.task import Task
from app.models.todo import Todo
from app.services import export_service, project_graph, project_service
from tests.external_util import seed


def _create(client, path, body):
    res = client.post(path, json=body)
    assert res.status_code in (200, 201), f"{path}: {res.status_code} {res.text}"
    return res.json()


# --- the guard that keeps it closed -------------------------------------------
def test_every_project_scoped_table_is_declared():
    """A new table with a project_id must travel or be excluded on purpose."""
    scoped = {
        table.name
        for table in SQLModel.metadata.sorted_tables
        if "project_id" in table.c
    }
    declared = {e.table for e in project_graph.ENTITIES} | set(project_graph.EXCLUDED)
    missing = scoped - declared
    assert not missing, (
        f"project-scoped table(s) in neither ENTITIES nor EXCLUDED: {sorted(missing)}. "
        "Decide whether they travel with a copy, and say so in project_graph.py."
    )


def test_excluded_names_are_real_tables():
    tables = {t.name for t in SQLModel.metadata.sorted_tables}
    assert set(project_graph.EXCLUDED) <= tables


def test_entity_keys_are_unique():
    keys = [e.key for e in project_graph.ENTITIES]
    payload_keys = [e.payload_key for e in project_graph.ENTITIES]
    assert len(set(keys)) == len(keys)
    assert len(set(payload_keys)) == len(payload_keys)


def test_parents_precede_children():
    """The single forward pass is only correct if a target is copied first."""
    seen: set[str] = {"project"}
    for entity in project_graph.ENTITIES:
        for target in entity.fk_remap.values():
            assert target in seen, f"{entity.key} points at {target}, which comes later"
        if entity.via_parent is not None:
            assert entity.via_parent[1] in seen
        seen.add(entity.key)


# --- sub-tasks survive a round trip -------------------------------------------
def test_export_import_remaps_parent_task(client):
    ws, proj = seed(client, "gph-sub")
    parent = _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Parent"})
    _create(client, f"/api/v1/projects/{proj}/tasks",
            {"title": "Child", "parent_task_id": parent["id"]})

    data = client.get(f"/api/v1/projects/{proj}/export").json()
    new = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert new.status_code in (200, 201), new.text
    copy = client.get(f"/api/v1/projects/{new.json()['id']}/export").json()

    by_title = {t["title"]: t for t in copy["tasks"]}
    copy_ids = {t["id"] for t in copy["tasks"]}
    assert by_title["Child"]["parent_task_id"] == by_title["Parent"]["id"]
    assert by_title["Child"]["parent_task_id"] in copy_ids  # never the source's
    assert by_title["Parent"]["id"] != parent["id"]


def test_duplicate_remaps_parent_task(client, session):
    ws, proj = seed(client, "gph-dup-sub")
    parent = _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Parent"})
    _create(client, f"/api/v1/projects/{proj}/tasks",
            {"title": "Child", "parent_task_id": parent["id"]})

    copy = project_service.duplicate_project(session, proj)
    tasks = session.exec(select(Task).where(Task.project_id == copy.id)).all()
    by_title = {t.title: t for t in tasks}
    assert by_title["Child"].parent_task_id == by_title["Parent"].id


# --- the three entities that used to vanish -----------------------------------
def _seed_extras(session: Session, project_id: str, phase_id: str | None = None) -> None:
    now = now_utc()
    session.add(StatusOption(
        id=new_id("sto"), project_id=project_id, entity_type="task", key="shipped",
        label="Shipped", sort_order=1, created_at=now, updated_at=now,
    ))
    session.add(CalendarEvent(
        id=new_id("cev"), project_id=project_id, phase_id=phase_id, title="Launch",
        start_at="2026-08-01", external_uid="remote-abc", etag="etag-1",
        created_at=now, updated_at=now,
    ))
    root = Todo(
        id=new_id("todo"), project_id=project_id, parent_id=None, label="Root",
        created_at=now, updated_at=now,
    )
    session.add(root)
    session.add(Todo(
        id=new_id("todo"), project_id=project_id, parent_id=root.id, label="Nested",
        created_at=now, updated_at=now,
    ))
    session.commit()


def test_export_carries_status_options_calendar_events_and_todos(client, session):
    ws, proj = seed(client, "gph-extras")
    phase = _create(client, f"/api/v1/projects/{proj}/phases", {"title": "P"})
    _seed_extras(session, proj, phase["id"])

    data = client.get(f"/api/v1/projects/{proj}/export").json()
    assert len(data["status_options"]) == 1
    assert len(data["calendar_events"]) == 1
    assert len(data["todos"]) == 2

    new = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert new.status_code in (200, 201), new.text
    copy_id = new.json()["id"]

    options = session.exec(select(StatusOption).where(StatusOption.project_id == copy_id)).all()
    events = session.exec(select(CalendarEvent).where(CalendarEvent.project_id == copy_id)).all()
    todos = session.exec(select(Todo).where(Todo.project_id == copy_id)).all()
    assert [o.key for o in options] == ["shipped"]
    assert [e.title for e in events] == ["Launch"]
    assert len(todos) == 2

    # The remote calendar identifiers belong to the original, not to the copy.
    assert events[0].external_uid is None and events[0].etag is None
    # phase_id followed the copy's own phase.
    copy_phases = {p["id"] for p in client.get(f"/api/v1/projects/{copy_id}/phases").json()}
    assert events[0].phase_id in copy_phases
    # Self-nesting todos are remapped, not left pointing at the source.
    nested = next(t for t in todos if t.label == "Nested")
    root = next(t for t in todos if t.label == "Root")
    assert nested.parent_id == root.id


def test_duplicate_carries_the_same_three(client, session):
    ws, proj = seed(client, "gph-dup-extras")
    _seed_extras(session, proj)

    copy = project_service.duplicate_project(session, proj)
    assert len(session.exec(select(StatusOption).where(StatusOption.project_id == copy.id)).all()) == 1
    events = session.exec(select(CalendarEvent).where(CalendarEvent.project_id == copy.id)).all()
    assert len(events) == 1 and events[0].external_uid is None
    todos = session.exec(select(Todo).where(Todo.project_id == copy.id)).all()
    assert len(todos) == 2
    nested = next(t for t in todos if t.label == "Nested")
    assert nested.parent_id == next(t for t in todos if t.label == "Root").id


def test_calendar_connection_never_travels(client, session):
    """Its tokens authorize the source account — a copy has no claim on them."""
    ws, proj = seed(client, "gph-conn")
    now = now_utc()
    session.add(CalendarConnection(
        id=new_id("ccn"), project_id=proj, provider="google", account_email="a@b.co",
        access_token_enc="enc", created_at=now, updated_at=now,
    ))
    session.commit()

    data = client.get(f"/api/v1/projects/{proj}/export").json()
    assert "calendar_connections" not in data
    copy = project_service.duplicate_project(session, proj)
    assert session.exec(
        select(CalendarConnection).where(CalendarConnection.project_id == copy.id)
    ).all() == []


# --- format versioning --------------------------------------------------------
def test_a_v1_payload_still_imports(client):
    """v1 files predate the three added entities; they simply lack those keys."""
    ws, proj = seed(client, "gph-v1")
    _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "Old task"})
    data = client.get(f"/api/v1/projects/{proj}/export").json()
    data["planarus_export"] = 1
    for key in ("status_options", "calendar_events", "todos"):
        data.pop(key, None)

    new = client.post("/api/v1/projects/import", json={"workspace_id": ws, "data": data})
    assert new.status_code in (200, 201), new.text
    copy = client.get(f"/api/v1/projects/{new.json()['id']}/export").json()
    assert [t["title"] for t in copy["tasks"]] == ["Old task"]
    assert copy["status_options"] == []


def test_a_future_version_is_refused(client, session):
    ws, proj = seed(client, "gph-v9")
    data = client.get(f"/api/v1/projects/{proj}/export").json()
    data["planarus_export"] = 99
    with pytest.raises(ValueError):
        export_service.import_project(session, ws, data)


# --- the manifest sees the same graph -----------------------------------------
def test_manifest_covers_checklist_items_and_the_new_entities(client, session):
    from app.sync.manifest import build_manifest

    ws, proj = seed(client, "gph-manifest")
    task = _create(client, f"/api/v1/projects/{proj}/tasks", {"title": "T"})
    _create(client, f"/api/v1/tasks/{task['id']}/checklist-items", {"label": "step one"})
    _seed_extras(session, proj)

    tables = {table for table, _ in build_manifest(session, proj)}
    assert {"checklistitem", "status_option", "calendar_event", "todo"} <= tables
