"""Two writers, one dependency graph: the cycle check must not be racy.

``_would_create_dependency_cycle`` reads the whole ``depends_on`` graph and then
inserts into it. Nothing in the schema can hold acyclicity — the canonical unique
index rejects the same edge twice, which is a different bug — so without an
explicit lock two transactions adding ``A -> B`` and ``B -> A`` both walk an
acyclic graph, both pass, and together commit a cycle.

Unlike most of this repo's concurrency guards, this one is *not* PostgreSQL-only:
SQLite ignores ``FOR UPDATE`` and takes its write lock at the first write, which
without ``lock_dependency_graph`` would land after the walk. So the same test body
runs on a file-backed SQLite (always) and on PostgreSQL (when
``PLANARUS_DATABASE_URL`` points at one — that is how CI runs it, see the
api-postgres job).
"""
import os
import threading
from uuid import uuid4

import app.models  # noqa: F401 — registers every table in SQLModel.metadata
import pytest
from app.core.utils import now_utc
from app.db.session import configure_sqlite_pragmas
from app.models.entity_connection import EntityConnection
from app.models.project import Project
from app.models.task import Task
from app.models.workspace import Workspace
from app.services import entity_connection_service as ecs
from sqlmodel import Session, SQLModel, create_engine, select

DSN = os.environ.get("PLANARUS_DATABASE_URL", "")

# How long writer 1 holds the lock before finishing. Writer 2 must not get
# through in that window; only an unlocked build can. Comfortably under SQLite's
# 5s busy_timeout, so a correct build waits rather than erroring.
LOCK_HELD_SECONDS = 1.0


@pytest.fixture(params=["sqlite", "postgres"])
def engine(request, tmp_path):
    if request.param == "postgres":
        if not DSN.startswith("postgresql"):
            pytest.skip("needs a PostgreSQL PLANARUS_DATABASE_URL (see the api-postgres CI job)")
        eng = create_engine(DSN)
    else:
        # File-backed, not in-memory: the race needs two real connections.
        eng = create_engine(
            f"sqlite:///{tmp_path / 'cycles.db'}",
            connect_args={"check_same_thread": False},
        )
        configure_sqlite_pragmas(eng)
    SQLModel.metadata.create_all(eng)  # no-op against the migrated CI schema
    yield eng
    eng.dispose()


def _seed(engine) -> tuple[str, str, str]:
    """A project with two tasks, and no connections between them yet."""
    suffix, now = uuid4().hex[:12], now_utc()
    ws, proj = f"ws-{suffix}", f"pr-{suffix}"
    task_a, task_b = f"tsk-a-{suffix}", f"tsk-b-{suffix}"
    with Session(engine) as s:
        s.add(Workspace(id=ws, name="W", slug=ws, created_at=now, updated_at=now))
        s.commit()
        s.add(Project(id=proj, workspace_id=ws, title="P", slug=proj,
                      created_at=now, updated_at=now))
        s.commit()
        s.add(Task(id=task_a, project_id=proj, title="A", created_at=now, updated_at=now))
        s.add(Task(id=task_b, project_id=proj, title="B", created_at=now, updated_at=now))
        s.commit()
    return proj, task_a, task_b


def _edge(source: str, target: str) -> dict:
    return {
        "relation_type": "depends_on",
        "source_entity_type": "task",
        "source_entity_id": source,
        "target_entity_type": "task",
        "target_entity_id": target,
    }


def test_opposing_dependency_edges_cannot_both_commit(engine):
    """``A -> B`` and ``B -> A`` raced: one wins, the other sees the cycle.

    Writer 1 takes the graph lock and holds it. Writer 2 then tries the reverse
    edge. If the lock is real, writer 2 blocks at ``lock_dependency_graph``, and
    when it finally walks the graph writer 1's edge is committed and visible, so
    it raises. If the lock is not real, writer 2 walks an empty graph, inserts,
    and the project ends up holding both halves of a cycle.
    """
    project_id, task_a, task_b = _seed(engine)

    lock_taken = threading.Event()      # writer 1 owns the graph
    writer2_started = threading.Event()  # writer 2 is issuing SQL now
    writer2_done = threading.Event()
    writer2_error: list[Exception] = []

    def writer2():
        lock_taken.wait(10)
        try:
            with Session(engine) as s:
                writer2_started.set()
                ecs.create_connection(s, project_id, _edge(task_b, task_a))
        except Exception as exc:  # noqa: BLE001 — asserted on below
            writer2_error.append(exc)
        finally:
            writer2_done.set()

    thread = threading.Thread(target=writer2, daemon=True)
    thread.start()

    with Session(engine) as s:
        ecs.lock_dependency_graph(s, project_id)
        lock_taken.set()
        assert writer2_started.wait(10), "writer 2 never issued its create"
        # Writer 2 is now queued behind the lock. Nothing it does may land.
        got_through = writer2_done.wait(LOCK_HELD_SECONDS)
        ecs.create_connection(s, project_id, _edge(task_a, task_b))

    thread.join(20)
    assert not got_through, (
        "writer 2 finished while writer 1 held the graph lock — the cycle check "
        "read a graph another writer was still adding to"
    )
    assert writer2_error, "writer 2 committed the reverse edge; the graph now has a cycle"
    assert "cycle" in str(writer2_error[0]), f"unexpected failure: {writer2_error[0]!r}"

    with Session(engine) as s:
        rows = s.exec(
            select(EntityConnection).where(EntityConnection.project_id == project_id)
        ).all()
    assert [(r.source_entity_id, r.target_entity_id) for r in rows] == [(task_a, task_b)]


def test_locking_the_graph_does_not_look_like_an_edit(engine):
    """The lock writes the project row; it must not make the project look edited."""
    project_id, task_a, task_b = _seed(engine)
    with Session(engine) as s:
        before = s.get(Project, project_id).updated_at

    with Session(engine) as s:
        ecs.create_connection(s, project_id, _edge(task_a, task_b))

    with Session(engine) as s:
        assert s.get(Project, project_id).updated_at == before
