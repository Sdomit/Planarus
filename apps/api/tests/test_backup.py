"""Phase 18.0 — verified local database backups (D42, D44).

Covers the properties that make a backup trustworthy rather than merely present:
the opt-in gate, a real ``VACUUM INTO`` snapshot that passes ``integrity_check``
*and actually contains the data*, retention that only ever deletes its own files,
the Postgres refusal, and the local-control gate on both routes.

The service tests run against a **file-backed** SQLite engine (not the in-memory
one in conftest) because that is what the production path snapshots.
"""
import sqlite3

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings as env
from app.core.exceptions import ConflictError
from app.db.session import configure_sqlite_pragmas
from app.models.project import Project
from app.models.workspace import Workspace
from app.core.utils import new_id, now_utc
from app.services import backup_service as svc
from app.services import settings_service
from tests.external_util import local_hdr


@pytest.fixture(name="backup_dir")
def backup_dir_fixture(tmp_path, monkeypatch):
    """Point the env ceiling at a throwaway directory."""
    target = tmp_path / "backups"
    monkeypatch.setattr(env, "backup_dir", str(target))
    return target


@pytest.fixture(name="file_session")
def file_session_fixture(tmp_path):
    """A real on-disk SQLite database — the thing backups actually snapshot."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'agentboard.db'}",
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_pragmas(engine)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _enable(session):
    settings_service.set_setting(session, "backup_enabled", True)
    session.commit()


def _seed_project(session, title="Backed up project"):
    now = now_utc()
    ws = Workspace(
        id=new_id("ws"), name="WS", slug="ws-backup", created_at=now, updated_at=now
    )
    session.add(ws)
    session.flush()
    proj = Project(
        id=new_id("proj"),
        workspace_id=ws.id,
        title=title,
        slug="p-backup",
        status="idea",
        created_at=now,
        updated_at=now,
    )
    session.add(proj)
    session.commit()
    return proj.id


# --- the opt-in gate ----------------------------------------------------------


def test_backup_is_disabled_by_default(file_session, backup_dir):
    with pytest.raises(ConflictError) as exc:
        svc.create_backup(file_session)
    assert "disabled" in str(exc.value).lower()
    assert not backup_dir.exists()  # nothing written while switched off


# --- the snapshot itself ------------------------------------------------------


def test_backup_snapshot_verifies_and_contains_the_data(file_session, backup_dir):
    project_id = _seed_project(file_session)
    _enable(file_session)

    result = svc.create_backup(file_session)

    written = backup_dir / result.backup.name
    assert written.is_file()
    assert result.backup.size_bytes > 0
    assert result.pruned == 0

    # A backup is only real if it restores: open the copy as its own database and
    # confirm both integrity and the actual row.
    probe = sqlite3.connect(written)
    try:
        assert probe.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = probe.execute(
            "SELECT id FROM project WHERE id = ?", (project_id,)
        ).fetchall()
    finally:
        probe.close()
    assert rows == [(project_id,)]


def test_backup_refused_on_non_sqlite(file_session, backup_dir, monkeypatch):
    _enable(file_session)
    monkeypatch.setattr(svc, "is_supported", lambda _session: False)
    with pytest.raises(ConflictError) as exc:
        svc.create_backup(file_session)
    # The message must point at the professional Postgres path, not just fail.
    assert "pg_dump" in str(exc.value)


# --- retention ----------------------------------------------------------------


def test_retention_keeps_newest_and_never_touches_foreign_files(
    file_session, backup_dir
):
    _enable(file_session)
    settings_service.set_setting(file_session, "backup_retention", 2)
    file_session.commit()

    svc.create_backup(file_session)
    svc.create_backup(file_session)
    backup_dir.mkdir(parents=True, exist_ok=True)
    bystander = backup_dir / "please-do-not-delete.db"
    bystander.write_text("not mine")

    third = svc.create_backup(file_session)

    remaining = [b.name for b in svc.list_backups()]
    assert len(remaining) == 2, remaining
    assert third.backup.name == remaining[0]  # newest first
    assert third.pruned == 1
    assert bystander.is_file()  # a foreign file is never a retention victim


def test_list_backups_ignores_non_matching_names(backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "agentboard-20260719T220501123456Z.db").write_bytes(b"x")
    (backup_dir / "agentboard-backup.db").write_bytes(b"x")
    (backup_dir / "notes.txt").write_bytes(b"x")
    assert [b.name for b in svc.list_backups()] == [
        "agentboard-20260719T220501123456Z.db"
    ]


def test_list_backups_empty_when_dir_missing(backup_dir):
    assert svc.list_backups() == []


# --- retention floor ----------------------------------------------------------


def test_retention_floor_prevents_deleting_every_copy(file_session):
    settings_service.set_setting(file_session, "backup_retention", 0)
    file_session.commit()
    assert settings_service.backup_retention(file_session) == 1


def test_retention_corrupt_value_falls_back(file_session):
    settings_service.set_setting(file_session, "backup_retention", "nonsense")
    file_session.commit()
    assert settings_service.backup_retention(file_session) == 7


# --- endpoint gates -----------------------------------------------------------


def test_backup_routes_require_local_control(client):
    assert client.get("/api/v1/backups").status_code == 401
    assert client.post("/api/v1/backups").status_code == 401


def test_list_backups_endpoint_returns_names_only(client, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "agentboard-20260719T220501123456Z.db").write_bytes(b"x")
    res = client.get("/api/v1/backups", headers=local_hdr(client))
    assert res.status_code == 200, res.text
    body = res.json()
    assert [b["name"] for b in body] == ["agentboard-20260719T220501123456Z.db"]
    # The server-owned directory is never disclosed to the client.
    assert str(backup_dir) not in res.text


def test_post_backup_endpoint_409_when_disabled(client, backup_dir):
    res = client.post("/api/v1/backups", headers=local_hdr(client))
    assert res.status_code == 409, res.text


# --- P18.4: the off-site copy (D44) -------------------------------------------
#
# On-disk-only is not a backup strategy: it survives a bad migration, not a dead
# disk. These pin that the push is opt-in, honest about where it cannot help, and
# — most importantly — never costs you the good local copy.


@pytest.fixture(name="memory_storage")
def memory_storage_fixture(monkeypatch):
    """Point the storage adapter at the in-memory backend (stands in for s3)."""
    from app import storage

    monkeypatch.setattr(env, "storage_backend", "memory")
    storage.reset_storage()
    yield storage
    storage.reset_storage()


def _enable_offsite(session):
    settings_service.set_setting(session, "backup_offsite", True)
    session.commit()


def test_offsite_is_off_by_default(file_session, backup_dir):
    _enable(file_session)
    result = svc.create_backup(file_session)
    assert result.offsite is None
    assert result.offsite_error is None


def test_offsite_refuses_the_local_backend_with_a_reason(file_session, backup_dir):
    """Pushing to "local" would write the copy beside the original — say so
    rather than reporting a success that protects nothing."""
    _enable(file_session)
    _enable_offsite(file_session)

    result = svc.create_backup(file_session)
    assert result.offsite is None
    assert "local" in (result.offsite_error or "")


def test_offsite_pushes_the_verified_copy(file_session, backup_dir, memory_storage):
    _enable(file_session)
    _enable_offsite(file_session)

    result = svc.create_backup(file_session)
    assert result.offsite_error is None
    assert result.offsite  # a backend location string
    # Assert the bytes actually landed, not merely that a location came back.
    pushed = memory_storage.get_storage().read_bytes(str(backup_dir), result.backup.name)
    assert pushed is not None
    assert pushed[:16] == b"SQLite format 3\x00"


def test_a_failed_push_never_costs_the_good_backup(
    file_session, backup_dir, memory_storage, monkeypatch
):
    """The local file is the deliverable. An upload failure degrades the run to
    'local only' and reports why — it must not abort a snapshot already written
    and integrity-checked."""
    _enable(file_session)
    _enable_offsite(file_session)

    def boom():
        raise RuntimeError("s3 down")

    monkeypatch.setattr(memory_storage, "get_storage", boom)

    result = svc.create_backup(file_session)
    assert result.offsite is None
    assert "s3 down" in (result.offsite_error or "")
    # The backup still exists and still passes its own integrity check.
    svc.verify_backup(result.backup.name)
