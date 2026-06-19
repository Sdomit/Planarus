from collections.abc import Generator

from sqlalchemy import event as sa_event
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings

connect_args: dict = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)

if settings.database_url.startswith("sqlite"):
    @sa_event.listens_for(engine, "connect")
    def _set_sqlite_wal(dbapi_conn, _record) -> None:
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    import app.models  # noqa: F401 — registers all SQLModel tables
    SQLModel.metadata.create_all(engine)
