"""Real two-session concurrency test for the approval apply path — PostgreSQL only.

The rest of the suite runs on in-memory SQLite, which *cannot* reproduce the bug
this guards: SQLite serialises writers, so the approved->applying CAS in
``apply()`` already holds the single writer lock across revalidation and the
write. On PostgreSQL (READ COMMITTED) nothing holds unless the target row is
explicitly locked, and a human edit landing in that window is silently
overwritten.

Skipped unless ``AGENTBOARD_DATABASE_URL`` points at PostgreSQL — that is how CI
runs it (see the api-postgres job). Locally it collects and skips.
"""
import os
import threading

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — registers every table in SQLModel.metadata
from app.core.utils import new_id, now_utc
from app.models.project import Project
from app.models.task import Task
from app.models.workspace import Workspace
from app.policy import handlers
from app.schemas.task import TaskUpdate
from app.services import approval_service, task_service

DSN = os.environ.get("AGENTBOARD_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DSN.startswith("postgresql"),
    reason="needs a PostgreSQL AGENTBOARD_DATABASE_URL (see the api-postgres CI job)",
)

# How long the human's UPDATE is given to prove it is *not* blocked. Only an
# unlocked (buggy) build can finish inside this window; a correct build blocks
# until apply commits. Overshooting costs one idle second, undershooting would
# fail a correct build, so this is deliberately generous for a loaded runner.
BLOCKED_PROBE_SECONDS = 2.0


@pytest.fixture(name="pg_engine")
def pg_engine_fixture():
    engine = create_engine(DSN)
    SQLModel.metadata.create_all(engine)  # no-op against the migrated CI schema
    yield engine
    engine.dispose()


def _seed(engine) -> tuple[str, str]:
    """A project with one task and an approved task.update proposal against it."""
    suffix, now = new_id()[:12], now_utc()
    with Session(engine) as s:
        s.add(Workspace(id=f"ws-{suffix}", name="W", slug=f"ws-{suffix}",
                        created_at=now, updated_at=now))
        s.commit()
        s.add(Project(id=f"pr-{suffix}", workspace_id=f"ws-{suffix}", title="P",
                      slug=f"pr-{suffix}", created_at=now, updated_at=now))
        s.commit()
        s.add(Task(id=f"tk-{suffix}", project_id=f"pr-{suffix}", title="original",
                   created_at=now, updated_at=now))
        s.commit()
        ar = approval_service.create_proposal(
            s,
            project_id=f"pr-{suffix}",
            action_type="task.update",
            target_entity_id=f"tk-{suffix}",
            patch={"title": "from-proposal"},
        )
        approval_service.approve(s, ar.id)
        return ar.id, f"tk-{suffix}"


def test_concurrent_human_edit_is_not_lost(pg_engine, monkeypatch):
    """A human write racing an apply must not be silently overwritten.

    apply() is paused *after* revalidation (which takes the row lock) and before
    the handler writes. The human then attempts their UPDATE on the same row. If
    the lock is held they block until apply commits and their write lands last;
    if it is not, they commit immediately and apply overwrites them.
    """
    approval_id, task_id = _seed(pg_engine)

    reached_handler = threading.Event()   # apply holds the lock, about to write
    human_started = threading.Event()     # human is issuing its UPDATE now
    human_finished = threading.Event()    # human's UPDATE committed
    human_blocked = threading.Event()     # human did NOT get through in time
    human_errors: list = []
    original_apply_action = handlers.apply_action

    def paused_apply_action(*args, **kwargs):
        reached_handler.set()
        # Only start timing once the human is actually issuing SQL, otherwise a
        # slow thread start would read as "blocked" and pass a broken build.
        if human_started.wait(10) and not human_finished.wait(BLOCKED_PROBE_SECONDS):
            human_blocked.set()
        return original_apply_action(*args, **kwargs)

    monkeypatch.setattr(handlers, "apply_action", paused_apply_action)

    def human_edit():
        try:
            reached_handler.wait(10)
            with Session(pg_engine) as s:
                human_started.set()
                task_service.update_task(s, task_id, TaskUpdate(title="from-human"))
        except Exception as exc:  # noqa: BLE001 — surfaced by the assert below
            human_errors.append(exc)
        finally:
            human_finished.set()

    human = threading.Thread(target=human_edit, daemon=True)
    human.start()
    with Session(pg_engine) as s:
        approval_service.apply(s, approval_id)
    human.join(20)

    assert not human_errors, f"the human's edit raised: {human_errors}"
    assert human_started.is_set(), "the human thread never issued its UPDATE"
    assert human_blocked.is_set(), (
        "the human's UPDATE completed while apply held the target — the row was "
        "not locked, so apply is about to overwrite a newer value"
    )
    with Session(pg_engine) as s:
        assert s.get(Task, task_id).title == "from-human", (
            "the human edit was lost: apply overwrote a value committed after "
            "its own revalidation"
        )
