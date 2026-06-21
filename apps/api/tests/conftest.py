import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — registers all tables in SQLModel.metadata
from app.db.session import configure_sqlite_pragmas, get_session
from app.main import app


@pytest.fixture(name="engine")
def engine_fixture():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Match production: enforce foreign keys (WAL is a no-op on in-memory DBs).
    configure_sqlite_pragmas(test_engine)
    SQLModel.metadata.create_all(test_engine)
    yield test_engine
    SQLModel.metadata.drop_all(test_engine)


@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(name="external_api")
def external_api_fixture(monkeypatch):
    """Enable the Phase 7C1 external API for the duration of a test + reset the
    in-process rate limiter (state is process-global). Disabled-by-default is
    restored automatically by monkeypatch."""
    from app.core.config import settings
    from app.core.rate_limit import limiter

    monkeypatch.setattr(settings, "external_api_enabled", True)
    limiter.reset()
    yield
    limiter.reset()
