"""DB-behaviour guards: WAL, foreign-key enforcement, and status CHECK."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.utils import new_id, now_utc
from app.db.session import configure_sqlite_pragmas
from app.models.project import Project
from app.models.workspace import Workspace


def test_wal_enabled_for_file_backed_sqlite(tmp_path) -> None:
    db_path = tmp_path / "wal_check.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    configure_sqlite_pragmas(engine)
    with engine.connect() as conn:
        mode = conn.execute(text("PRAGMA journal_mode")).scalar()
    engine.dispose()
    assert str(mode).lower() == "wal"


def test_foreign_keys_pragma_on(session) -> None:
    # The test engine applies the same pragmas as production.
    result = session.execute(text("PRAGMA foreign_keys")).scalar()
    assert result == 1


def test_foreign_keys_enforced(session) -> None:
    orphan = Project(
        id=new_id("proj"),
        workspace_id="ws_does_not_exist",
        title="Orphan",
        slug="orphan",
        status="idea",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(orphan)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_status_check_constraint_rejects_invalid(session) -> None:
    now = now_utc()
    workspace = Workspace(
        id=new_id("ws"), name="W", slug="chk-ws", created_at=now, updated_at=now
    )
    session.add(workspace)
    session.commit()

    bad = Project(
        id=new_id("proj"),
        workspace_id=workspace.id,
        title="Bad status",
        slug="bad-status",
        status="not_a_real_status",
        created_at=now,
        updated_at=now,
    )
    session.add(bad)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
