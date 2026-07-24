import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — registers all tables in SQLModel.metadata
from app.core.config import settings
from app.db.session import configure_sqlite_pragmas, get_session
from app.main import app


@pytest.fixture(autouse=True)
def _default_projects_root(tmp_path, monkeypatch):
    """#115: auth-enabled mode derives each project root under PLANARUS_PROJECTS_ROOT.

    Give every test an isolated, real base so auth-mode project creation works
    without editing all 17 auth fixtures. Local-mode tests ignore it entirely
    (they use the operator-supplied folder_path). A test that needs it unset
    (e.g. the fail-closed startup check) overrides this with its own monkeypatch.
    """
    base = tmp_path / "managed-projects"
    base.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "projects_root", str(base))


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
    # base_url picks a Host the app-wide allowlist accepts (the default
    # "testserver" is deliberately treated as a foreign host in guard tests).
    yield TestClient(app, base_url="http://localhost")
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
