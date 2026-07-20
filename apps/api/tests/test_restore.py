"""Phase 18.3 — restore, proven end to end (D43).

The point of this file is the round trip: a backup is only a backup if the data
actually comes back. It also pins the properties that make restore survivable —
a corrupt backup never overwrites good data, the previous state is always kept,
and a stale WAL sidecar can never outlive the database file it belonged to.

Everything here runs against a real on-disk database, because that is what a
restore replaces.
"""
import sqlite3
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app import jobs
from app.core.config import settings as env
from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc
from app.db.session import configure_sqlite_pragmas
from app.models.project import Project
from app.models.workspace import Workspace
from app.services import backup_service as svc
from app.services import settings_service


@pytest.fixture(name="live_db")
def live_db_fixture(tmp_path, monkeypatch):
    """A real database + backup directory wired through *config*, which is how the
    CLI reads them — during a restore the app is stopped, so there is no engine."""
    db = tmp_path / "agentboard.db"
    monkeypatch.setattr(env, "database_url", f"sqlite:///{db}")
    monkeypatch.setattr(env, "backup_dir", str(tmp_path / "backups"))
    return db


def _make_backup(db: Path) -> tuple[str, str]:
    """Seed a project, back it up, release the file. Returns (backup name, id)."""
    engine = create_engine(
        f"sqlite:///{db}", connect_args={"check_same_thread": False}
    )
    configure_sqlite_pragmas(engine)
    SQLModel.metadata.create_all(engine)
    now = now_utc()
    with Session(engine) as session:
        ws = Workspace(
            id=new_id("ws"), name="WS", slug="ws-r", created_at=now, updated_at=now
        )
        session.add(ws)
        session.flush()
        proj = Project(
            id=new_id("proj"),
            workspace_id=ws.id,
            title="Survivor",
            slug="p-r",
            status="idea",
            created_at=now,
            updated_at=now,
        )
        session.add(proj)
        settings_service.set_setting(session, "backup_enabled", True)
        session.commit()
        project_id = proj.id
        name = svc.create_backup(session).backup.name
    engine.dispose()  # Windows: the handle must be released before the file moves
    return name, project_id


def _project_ids(db: Path) -> list[str]:
    probe = sqlite3.connect(db)
    try:
        return [row[0] for row in probe.execute("SELECT id FROM project").fetchall()]
    finally:
        probe.close()


def _lose_the_data(db: Path) -> None:
    probe = sqlite3.connect(db)
    try:
        probe.execute("DELETE FROM project")
        probe.commit()
    finally:
        probe.close()


# --- the round trip -----------------------------------------------------------


def test_restore_round_trip_brings_the_data_back(live_db):
    name, project_id = _make_backup(live_db)
    _lose_the_data(live_db)
    assert _project_ids(live_db) == []

    result = svc.restore_backup(name)

    assert result.restored_from == name
    assert _project_ids(live_db) == [project_id]  # the whole point
    assert result.displaced  # the previous state was preserved, not discarded


# --- the safety properties ----------------------------------------------------


def test_corrupt_backup_never_overwrites_good_data(live_db):
    name, project_id = _make_backup(live_db)
    (svc.backup_dir() / name).write_bytes(b"this is not a database")

    with pytest.raises(ConflictError) as exc:
        svc.restore_backup(name)

    assert "integrity" in str(exc.value).lower()
    # Verification runs before anything is moved, so the live DB is untouched.
    assert _project_ids(live_db) == [project_id]


def test_restore_displaces_stale_wal_sidecars(live_db):
    name, project_id = _make_backup(live_db)
    stale = Path(f"{live_db}-wal")
    stale.write_bytes(b"stale wal frames from the old database")

    result = svc.restore_backup(name)

    # Leaving this behind would let SQLite replay the old database's frames over
    # the restored file — the corruption path this guards.
    assert not stale.exists()
    assert any("-wal.pre-restore-" in d for d in result.displaced)
    assert _project_ids(live_db) == [project_id]


def test_verify_does_not_delete_a_failing_backup(live_db):
    name, _ = _make_backup(live_db)
    path = svc.backup_dir() / name
    path.write_bytes(b"corrupt")

    with pytest.raises(ConflictError):
        svc.verify_backup(name)

    # Inspecting must never destroy what might be the operator's only copy.
    assert path.is_file()


def test_resolve_backup_rejects_traversal_and_unknown_names(live_db):
    for bad in ("../../etc/passwd", "agentboard.db", "..", "sub/dir.db"):
        with pytest.raises(ConflictError):
            svc.resolve_backup(bad)
    # Well-formed but absent is a miss, not a traversal.
    with pytest.raises(ConflictError, match="not found"):
        svc.resolve_backup("agentboard-20260719T220501123456Z.db")


# --- the CLI ------------------------------------------------------------------


def test_cli_restore_refuses_without_yes(live_db):
    name, project_id = _make_backup(live_db)
    _lose_the_data(live_db)

    assert jobs.main(["restore", name]) == jobs.EXIT_REFUSED
    assert _project_ids(live_db) == []  # refused means nothing happened


def test_cli_restore_with_yes_round_trips(live_db):
    name, project_id = _make_backup(live_db)
    _lose_the_data(live_db)

    assert jobs.main(["restore", name, "--yes"]) == jobs.EXIT_OK
    assert _project_ids(live_db) == [project_id]


def test_cli_verify_exit_codes(live_db):
    # Nothing to verify yet — a failure the scheduler can see.
    assert jobs.main(["verify"]) == jobs.EXIT_FAILED

    name, _ = _make_backup(live_db)
    assert jobs.main(["verify"]) == jobs.EXIT_OK  # defaults to newest
    assert jobs.main(["verify", name]) == jobs.EXIT_OK

    (svc.backup_dir() / name).write_bytes(b"corrupt")
    assert jobs.main(["verify", name]) == jobs.EXIT_FAILED
