"""Phase 10.6b — sync apply + baseline persistence (end-to-end).

Two file-backed SQLite replicas are given a common base (via the P10.5 ETL), then
diverged. We diff against the base, apply the plan, and assert both replicas
converge with no data lost — plus the conflict path blocks apply until resolved,
and the baseline round-trips.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.db.session import configure_sqlite_pragmas
from app.etl import copy_all
from app.models.task import Task
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.schemas.workspace import WorkspaceCreate
from app.sync import (
    apply_plan,
    build_manifest,
    load_baseline,
    resolve_conflicts,
    save_baseline,
    three_way_diff,
)
from app.services import project_service, task_service, workspace_service


def _db(path):
    url = f"sqlite:///{path}"
    engine = create_engine(url)
    configure_sqlite_pragmas(engine)
    SQLModel.metadata.create_all(engine)
    return url, engine


@pytest.fixture(name="replicas")
def replicas_fixture(tmp_path):
    """A local + remote replica sharing an identical base (2 tasks)."""
    local_url, local = _db(tmp_path / "local.db")
    remote_url, remote = _db(tmp_path / "remote.db")
    with Session(local) as s:
        ws = workspace_service.create_workspace(s, WorkspaceCreate(name="W", slug="acme"))
        p = project_service.create_project(
            s, ProjectCreate(workspace_id=ws.id, title="P", slug="proj")
        )
        t1 = task_service.create_task(s, p.id, TaskCreate(title="A"))
        t2 = task_service.create_task(s, p.id, TaskCreate(title="B"))
        pid, t1_id, t2_id = p.id, t1.id, t2.id
    copy_all(local_url, remote_url)  # establish identical base
    with Session(local) as s:
        base = build_manifest(s, pid)
    return {
        "local": local, "remote": remote, "pid": pid,
        "t1": t1_id, "t2": t2_id, "base": base,
    }


def _edit_title(engine, task_id, title):
    with Session(engine) as s:
        t = s.get(Task, task_id)
        t.title = title
        s.add(t)
        s.commit()


def test_one_sided_edits_converge(replicas):
    r = replicas
    _edit_title(r["local"], r["t1"], "A-local")   # local changes t1
    _edit_title(r["remote"], r["t2"], "B-remote")  # remote changes t2

    with Session(r["local"]) as sl, Session(r["remote"]) as sr:
        plan = three_way_diff(r["base"], build_manifest(sl, r["pid"]), build_manifest(sr, r["pid"]))
        assert not plan.has_conflicts
        apply_plan(sl, sr, plan)

        # Both replicas now carry both edits.
        assert build_manifest(sl, r["pid"]) == build_manifest(sr, r["pid"])
        assert sr.get(Task, r["t1"]).title == "A-local"   # pushed local→remote
        assert sl.get(Task, r["t2"]).title == "B-remote"  # pulled remote→local


def test_divergent_edit_conflicts_then_resolves(replicas):
    r = replicas
    _edit_title(r["local"], r["t1"], "local-wins")
    _edit_title(r["remote"], r["t1"], "remote-wins")  # same entity, both sides

    with Session(r["local"]) as sl, Session(r["remote"]) as sr:
        plan = three_way_diff(r["base"], build_manifest(sl, r["pid"]), build_manifest(sr, r["pid"]))
        assert plan.has_conflicts
        with pytest.raises(ValueError, match="unresolved conflicts"):
            apply_plan(sl, sr, plan)

        resolved = resolve_conflicts(plan, {("task", r["t1"]): "local"})
        apply_plan(sl, sr, resolved)
        assert sr.get(Task, r["t1"]).title == "local-wins"
        assert build_manifest(sl, r["pid"]) == build_manifest(sr, r["pid"])


def test_create_and_delete_propagate(replicas):
    r = replicas
    with Session(r["local"]) as s:  # local creates a new task
        new = task_service.create_task(s, r["pid"], TaskCreate(title="C"))
        new_id = new.id
    with Session(r["remote"]) as s:  # remote deletes t2
        s.delete(s.get(Task, r["t2"]))
        s.commit()

    with Session(r["local"]) as sl, Session(r["remote"]) as sr:
        plan = three_way_diff(r["base"], build_manifest(sl, r["pid"]), build_manifest(sr, r["pid"]))
        apply_plan(sl, sr, plan)
        assert sr.get(Task, new_id) is not None       # create pushed to remote
        assert sl.get(Task, r["t2"]) is None           # delete pulled to local
        assert build_manifest(sl, r["pid"]) == build_manifest(sr, r["pid"])


def test_baseline_roundtrip(replicas):
    r = replicas
    with Session(r["local"]) as s:
        assert load_baseline(s, r["pid"]) is None  # never synced
        manifest = build_manifest(s, r["pid"])
        save_baseline(s, r["pid"], manifest)
        assert load_baseline(s, r["pid"]) == manifest
        # upsert (one row per project)
        save_baseline(s, r["pid"], {})
        assert load_baseline(s, r["pid"]) == {}
