"""#114 — the two admin-cardinality invariants, under concurrency.

Both bugs the audit found are check-then-act races, so both need more than one
connection to reproduce: the shared in-memory fixture hands every Session the
same connection and can never show them. These tests use a file-backed SQLite
database with independent sessions — the deterministic interleavings run here,
and the threaded PostgreSQL variants live in ``test_admin_concurrency_pg.py``.

Invariant 1 — exactly one account may bootstrap to admin.
Invariant 2 — the last active admin can be neither demoted nor deactivated.
"""
import threading

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401 — registers every table in SQLModel.metadata
from app.core.config import settings
from app.core.exceptions import ConflictError
from app.core.utils import new_id, now_utc
from app.db.session import configure_sqlite_pragmas
from app.models.setting import Setting
from app.models.user import User
from app.services import admin_service, auth_service

PASSWORD = "correct-horse-battery"


@pytest.fixture(name="file_engine")
def file_engine_fixture(tmp_path):
    """A real on-disk SQLite database, so two Sessions are two connections."""
    # Deliberately NOT StaticPool (which conftest uses for its in-memory engine):
    # pooling one connection would hand both Sessions the same transaction and
    # quietly turn every race below into a no-op.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'invariants.db'}",
        connect_args={"check_same_thread": False},
    )
    configure_sqlite_pragmas(engine)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(name="password_auth")
def password_auth_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_password_enabled", True)
    yield


def _admin(session: Session, email: str) -> User:
    user = User(
        id=new_id("usr"),
        email=email,
        display_name=email.split("@")[0],
        is_admin=True,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(user)
    session.commit()
    return user


# --- invariant 1: exactly one bootstrap ---------------------------------------
def test_first_account_still_bootstraps(session, password_auth):
    user, _ = auth_service.register_password_user(session, "first@acme.co", PASSWORD, None)
    assert user.is_admin is True
    assert session.exec(
        select(Setting).where(Setting.key == auth_service.BOOTSTRAP_CLAIM_KEY)
    ).first() is not None


def test_a_lost_claim_still_registers_the_account(session, password_auth):
    """The loser of the race registers normally — it just isn't admin.

    Reproduces the losing side directly: the claim row exists while the accounts
    table is still empty, exactly the state the second of two racing
    registrations finds when it reaches its INSERT.
    """
    session.add(
        Setting(key=auth_service.BOOTSTRAP_CLAIM_KEY, value="true", updated_at=now_utc())
    )
    session.commit()
    user, token = auth_service.register_password_user(session, "second@acme.co", PASSWORD, None)
    assert user.is_admin is False
    assert token  # a session was still opened
    assert session.get(User, user.id) is not None  # the savepoint took only the claim


def test_two_racing_registrations_produce_exactly_one_admin(file_engine, password_auth):
    """The real thing: two threads registering into an empty server at once."""
    ready = threading.Barrier(2)
    errors: list = []

    def register(email: str) -> None:
        try:
            ready.wait(10)
            with Session(file_engine) as s:
                auth_service.register_password_user(s, email, PASSWORD, None)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assert below
            errors.append(exc)

    threads = [
        threading.Thread(target=register, args=(f"racer{i}@acme.co",), daemon=True)
        for i in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert not errors, f"a registration raised: {errors}"
    with Session(file_engine) as s:
        users = s.exec(select(User)).all()
        assert len(users) == 2
        assert [u.is_admin for u in users].count(True) == 1


# --- invariant 2: never zero active admins ------------------------------------
def test_last_admin_cannot_be_demoted_or_deactivated(session):
    only = _admin(session, "only@acme.co")
    with pytest.raises(ConflictError):
        admin_service.set_admin(session, only, False)
    with pytest.raises(ConflictError):
        admin_service.set_active(session, only, False)
    session.refresh(only)
    assert only.is_admin and only.is_active


def test_concurrent_self_demotions_leave_one_admin(file_engine):
    """The audit's scenario: two admins each pass "another admin exists", then
    both write. The second demotion must lose."""
    with Session(file_engine) as setup:
        a = _admin(setup, "a@acme.co").id
        b = _admin(setup, "b@acme.co").id

    with Session(file_engine) as s1, Session(file_engine) as s2:
        # Both transactions read a world with two admins before either writes.
        user_a, user_b = s1.get(User, a), s2.get(User, b)
        assert user_a.is_admin and user_b.is_admin
        admin_service.set_admin(s1, user_a, False)  # commits: A is no longer admin
        with pytest.raises(ConflictError):
            admin_service.set_admin(s2, user_b, False)

    with Session(file_engine) as check:
        admins = check.exec(
            select(User).where(User.is_admin == True)  # noqa: E712
        ).all()
        assert [u.id for u in admins] == [b]


def test_concurrent_demote_and_deactivate_leave_one_admin(file_engine):
    """The same race across the two different operations."""
    with Session(file_engine) as setup:
        a = _admin(setup, "a@acme.co").id
        b = _admin(setup, "b@acme.co").id

    with Session(file_engine) as s1, Session(file_engine) as s2:
        user_a, user_b = s1.get(User, a), s2.get(User, b)
        assert user_a.is_admin and user_b.is_admin
        admin_service.set_admin(s1, user_a, False)
        with pytest.raises(ConflictError):
            admin_service.set_active(s2, user_b, False)

    with Session(file_engine) as check:
        survivor = check.get(User, b)
        assert survivor.is_admin and survivor.is_active


def test_simultaneous_self_demotions_race_for_real(file_engine):
    """Both admins demote themselves at the same instant, from two connections.

    The deterministic cases above pin the contract; this one drives it as an
    actual race. SQLite serialises the two writers, so the conditional UPDATE's
    EXISTS is evaluated under the write lock and the second one matches nothing.
    The PostgreSQL variant (``test_admin_concurrency_pg.py``) is where write skew
    would otherwise slip through.
    """
    with Session(file_engine) as setup:
        ids = [_admin(setup, "a@acme.co").id, _admin(setup, "b@acme.co").id]

    ready = threading.Barrier(2)
    refused: list = []
    unexpected: list = []

    def demote(user_id: str) -> None:
        try:
            with Session(file_engine) as s:
                user = s.get(User, user_id)
                ready.wait(10)
                admin_service.set_admin(s, user, False)
        except ConflictError:
            refused.append(user_id)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assert below
            unexpected.append(exc)

    threads = [threading.Thread(target=demote, args=(i,), daemon=True) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)

    assert not unexpected, f"a demotion raised something else: {unexpected}"
    assert len(refused) == 1, "exactly one demotion must be refused"
    with Session(file_engine) as check:
        admins = check.exec(
            select(User).where(User.is_admin == True)  # noqa: E712
        ).all()
        assert len(admins) == 1


def test_demoting_a_non_last_admin_still_works(file_engine):
    with Session(file_engine) as setup:
        a = _admin(setup, "a@acme.co").id
        _admin(setup, "b@acme.co")

    with Session(file_engine) as s:
        admin_service.set_admin(s, s.get(User, a), False)
        assert s.get(User, a).is_admin is False
