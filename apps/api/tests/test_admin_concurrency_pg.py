"""Real two-session admin-invariant concurrency — PostgreSQL only (#114).

SQLite serialises writers, so ``tests/test_admin_invariants.py`` can prove the
last-active-admin rule there with the conditional UPDATE alone. PostgreSQL under
READ COMMITTED cannot: two transactions demoting *different* rows each evaluate
"another active admin exists" against their own snapshot, both find one, and both
commit — textbook write skew, and the exact scenario the audit describes. Only
the explicit ``FOR UPDATE`` over the admin set stops it, and only this test can
show that.

The bootstrap half is not repeated here: it is a primary-key collision, which
behaves identically on both engines and is already covered on SQLite (including
a threaded race).

Skipped unless ``PLANARUS_DATABASE_URL`` points at PostgreSQL — that is how CI
runs it (see the api-postgres job). Locally it collects and skips.
"""
import os
import threading
from uuid import uuid4

import app.models  # noqa: F401 — registers every table in SQLModel.metadata
import pytest
from app.core.exceptions import ConflictError
from app.core.utils import now_utc
from app.models.user import User
from app.services import admin_service
from sqlmodel import Session, SQLModel, create_engine, select

DSN = os.environ.get("PLANARUS_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not DSN.startswith("postgresql"),
    reason="needs a PostgreSQL PLANARUS_DATABASE_URL (see the api-postgres CI job)",
)


@pytest.fixture(name="pg_engine")
def pg_engine_fixture():
    engine = create_engine(DSN)
    SQLModel.metadata.create_all(engine)  # no-op against the migrated CI schema
    yield engine
    engine.dispose()


@pytest.fixture(name="two_admins")
def two_admins_fixture(pg_engine):
    """Exactly two active admins, and nothing else admin, for the length of the test."""
    suffix = uuid4().hex[:12]
    ids = [f"usr-{suffix}-a", f"usr-{suffix}-b"]
    with Session(pg_engine) as s:
        others = s.exec(
            select(User).where(
                User.is_admin == True,  # noqa: E712
                User.is_active == True,  # noqa: E712
            )
        ).all()
        assert not others, (
            "another test left an active admin behind; this test needs to be the "
            f"only source of admins: {[u.id for u in others]}"
        )
        for uid in ids:
            s.add(
                User(
                    id=uid,
                    email=f"{uid}@example.test",
                    display_name=uid,
                    is_admin=True,
                    created_at=now_utc(),
                    updated_at=now_utc(),
                )
            )
        s.commit()
    yield ids
    with Session(pg_engine) as s:
        for uid in ids:
            row = s.get(User, uid)
            if row is not None:
                s.delete(row)
        s.commit()


def test_concurrent_self_demotions_cannot_both_win(pg_engine, two_admins):
    """Two admins demote themselves at once; the server must keep one."""
    ready = threading.Barrier(2)
    refused: list = []
    unexpected: list = []

    def demote(user_id: str) -> None:
        try:
            with Session(pg_engine) as s:
                user = s.get(User, user_id)
                ready.wait(15)
                admin_service.set_admin(s, user, False)
        except ConflictError:
            refused.append(user_id)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assert below
            unexpected.append(exc)

    threads = [threading.Thread(target=demote, args=(i,), daemon=True) for i in two_admins]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)

    assert not unexpected, f"a demotion raised something else: {unexpected}"
    assert len(refused) == 1, (
        "both demotions were accepted — the admin set was not locked, so each "
        "transaction read a snapshot in which the other was still an admin"
    )
    with Session(pg_engine) as s:
        survivors = [uid for uid in two_admins if s.get(User, uid).is_admin]
        assert len(survivors) == 1


def test_concurrent_demote_and_deactivate_cannot_both_win(pg_engine, two_admins):
    """The same write skew across the two different operations."""
    ready = threading.Barrier(2)
    refused: list = []
    unexpected: list = []

    def run(user_id: str, demote: bool) -> None:
        try:
            with Session(pg_engine) as s:
                user = s.get(User, user_id)
                ready.wait(15)
                if demote:
                    admin_service.set_admin(s, user, False)
                else:
                    admin_service.set_active(s, user, False)
        except ConflictError:
            refused.append(user_id)
        except Exception as exc:  # noqa: BLE001 — surfaced by the assert below
            unexpected.append(exc)

    threads = [
        threading.Thread(target=run, args=(two_admins[0], True), daemon=True),
        threading.Thread(target=run, args=(two_admins[1], False), daemon=True),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)

    assert not unexpected, f"an operation raised something else: {unexpected}"
    assert len(refused) == 1
    with Session(pg_engine) as s:
        live = [
            uid for uid in two_admins if s.get(User, uid).is_admin and s.get(User, uid).is_active
        ]
        assert len(live) == 1, "no active admin survived the race"
