from collections.abc import Generator

from sqlalchemy import event as sa_event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings


def configure_sqlite_pragmas(engine: Engine) -> None:
    """Register a connect listener that enables WAL and foreign-key enforcement.

    SQLite defaults to ``foreign_keys=OFF`` and the rollback journal; both must be
    set per-connection. Applied to the app engine here and to the test engine in
    `tests/conftest.py` so behaviour matches. WAL is a no-op on in-memory DBs.
    """

    @sa_event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL allows many readers + one writer; busy_timeout makes a writer wait
        # briefly (rather than failing immediately) when the API and the Phase 7B
        # MCP process contend for the write lock. Bounded so a stuck lock still
        # surfaces as a normal, handleable error rather than hanging forever.
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    configure_sqlite_pragmas(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    """Create all tables directly from SQLModel metadata.

    NOT called on app startup — Alembic is the canonical schema path
    (``cd apps/api && alembic upgrade head``). Retained for ad-hoc local/dev
    scripting and is not part of the request lifecycle.
    """
    import app.models  # noqa: F401 — registers all SQLModel tables

    SQLModel.metadata.create_all(engine)
