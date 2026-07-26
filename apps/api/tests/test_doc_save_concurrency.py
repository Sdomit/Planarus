"""#156: the doc save lock, and the two states `null` could never reach.

Two defects, both in `doc_service.update_doc`:

- the optimistic lock was read-then-write with no atomic guard, so two saves
  from the same version both passed and the second silently overwrote the first;
- every field keyed off `is not None`, making null indistinguishable from
  omitted, so `archived_at` and `parent_doc_id` could never be cleared.
"""
import pytest
from app.core.exceptions import ConflictError
from app.models.doc import Doc
from app.schemas.doc import DocCreate, DocUpdate
from app.services import doc_service
from fastapi.testclient import TestClient
from sqlalchemy import update as sa_update
from sqlmodel import Session


def _project(client: TestClient, suffix: str) -> str:
    ws = client.post(
        "/api/v1/workspaces", json={"name": "W", "slug": f"ws-{suffix}"}
    ).json()
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()["id"]


def _doc(session: Session, pid: str, title: str = "D", **kw) -> Doc:
    return doc_service.create_doc(
        session, pid, DocCreate(title=title, doc_type="note", **kw)
    )


# --- null now clears a nullable column ---------------------------------------


def test_archived_doc_can_be_unarchived(client: TestClient, session: Session) -> None:
    doc = _doc(session, _project(client, "156a"))
    doc = doc_service.update_doc(
        session, doc.id, DocUpdate(version=doc.version, archived_at="2026-07-26T00:00:00+00:00")
    )
    assert doc.archived_at is not None

    doc = doc_service.update_doc(
        session, doc.id, DocUpdate(version=doc.version, archived_at=None)
    )
    assert doc.archived_at is None


def test_child_doc_can_move_back_to_root(client: TestClient, session: Session) -> None:
    pid = _project(client, "156b")
    parent = _doc(session, pid, "Parent")
    child = _doc(session, pid, "Child", parent_doc_id=parent.id)
    assert child.parent_doc_id == parent.id

    child = doc_service.update_doc(
        session, child.id, DocUpdate(version=child.version, parent_doc_id=None)
    )
    assert child.parent_doc_id is None


def test_color_clears_by_null_and_by_the_legacy_sentinel(
    client: TestClient, session: Session
) -> None:
    """"default" predates this fix and stays accepted; null now works too."""
    pid = _project(client, "156c")
    for clear_with in (None, "default"):
        doc = _doc(session, pid, f"D{clear_with}", color="teal")
        assert doc.color == "teal"
        doc = doc_service.update_doc(
            session, doc.id, DocUpdate(version=doc.version, color=clear_with)
        )
        assert doc.color is None, f"clearing with {clear_with!r} failed"


def test_omitting_a_field_still_means_unchanged(
    client: TestClient, session: Session
) -> None:
    """The other half of presence semantics: absent must not be read as null."""
    pid = _project(client, "156d")
    parent = _doc(session, pid, "Parent")
    child = _doc(session, pid, "Child", parent_doc_id=parent.id, color="teal")
    child = doc_service.update_doc(
        session, child.id, DocUpdate(version=child.version, title="Renamed")
    )
    assert child.title == "Renamed"
    assert child.parent_doc_id == parent.id, "omitted parent_doc_id was cleared"
    assert child.color == "teal", "omitted color was cleared"
    assert child.archived_at is None


def test_null_on_a_not_null_column_is_still_ignored(
    client: TestClient, session: Session
) -> None:
    """title cannot hold NULL, so an explicit null has no state to express."""
    doc = _doc(session, _project(client, "156e"), "Keep me")
    doc = doc_service.update_doc(
        session, doc.id, DocUpdate(version=doc.version, title=None, status="draft")
    )
    assert doc.title == "Keep me"
    assert doc.status == "draft"


# --- the lock is now atomic ---------------------------------------------------
#
# #99: these three asserted `pytest.raises(LookupError)`, which pinned the bug
# rather than the behaviour. A version conflict is not a missing row, and the
# app-wide convention maps LookupError to 404 — so `endpoints/docs.py` carried a
# local `except LookupError -> 409` to invert it back. The service now raises
# ConflictError and the router carries nothing. What these tests actually care
# about — that the losing writer is rejected and writes nothing — is unchanged.


def test_stale_version_is_rejected(client: TestClient, session: Session) -> None:
    doc = _doc(session, _project(client, "156f"))
    stale = doc.version
    doc_service.update_doc(session, doc.id, DocUpdate(version=stale, title="First"))

    with pytest.raises(ConflictError):
        doc_service.update_doc(session, doc.id, DocUpdate(version=stale, title="Second"))


def test_a_writer_losing_the_race_mid_save_is_rejected(
    client: TestClient, session: Session, monkeypatch
) -> None:
    """The lost update itself — the window between the pre-check and the write.

    A competing commit placed *before* update_doc is called proves nothing: the
    pre-check re-reads and catches it, so such a test passes against the broken
    read-then-write code too (it did, on the first attempt at this file).

    The only interesting interleaving is: pre-check reads version N and passes →
    another writer commits N+1 → this caller's write lands. Reproduced by hooking
    `now_utc`, which update_doc calls after the pre-check and before the write,
    and committing the competing update from inside it.
    """
    doc = _doc(session, _project(client, "156g"), "Original")
    payload = DocUpdate(version=doc.version, title="Writer A")
    original_version = doc.version
    fired: list[bool] = []

    real_now = doc_service.now_utc

    def _commit_a_competing_write() -> str:
        if not fired:
            fired.append(True)
            session.execute(
                sa_update(Doc)
                .where(Doc.id == doc.id)
                .values(version=original_version + 1, title="Writer B")
            )
            session.commit()
        return real_now()

    monkeypatch.setattr(doc_service, "now_utc", _commit_a_competing_write)

    with pytest.raises(ConflictError):
        doc_service.update_doc(session, doc.id, payload)

    assert fired, "the competing write never ran — the hook missed its window"
    session.expire_all()
    fresh = session.get(Doc, doc.id)
    assert fresh.title == "Writer B", "Writer A overwrote a newer commit"
    assert fresh.version == original_version + 1, "version was double-bumped"


def test_a_rejected_save_writes_nothing(client: TestClient, session: Session) -> None:
    """A losing writer must not leave a partial update or bump the version."""
    doc = _doc(session, _project(client, "156h"), "Original")
    stale = doc.version
    doc_service.update_doc(session, doc.id, DocUpdate(version=stale, title="Winner"))

    with pytest.raises(ConflictError):
        doc_service.update_doc(
            session, doc.id, DocUpdate(version=stale, title="Loser", status="draft")
        )

    session.expire_all()
    fresh = session.get(Doc, doc.id)
    assert fresh.title == "Winner"
    assert fresh.version == stale + 1


def test_conflict_surfaces_as_409(client: TestClient, session: Session) -> None:
    pid = _project(client, "156i")
    doc = _doc(session, pid)
    stale = doc.version
    assert client.patch(
        f"/api/v1/docs/{doc.id}", json={"version": stale, "title": "First"}
    ).status_code == 200
    res = client.patch(
        f"/api/v1/docs/{doc.id}", json={"version": stale, "title": "Second"}
    )
    assert res.status_code == 409


def test_unarchive_over_http(client: TestClient, session: Session) -> None:
    """The route the UI actually uses — DocUpdate is the only write path."""
    pid = _project(client, "156j")
    doc = _doc(session, pid)
    archived = client.patch(
        f"/api/v1/docs/{doc.id}",
        json={"version": doc.version, "archived_at": "2026-07-26T00:00:00+00:00"},
    ).json()
    assert archived["archived_at"] is not None

    restored = client.patch(
        f"/api/v1/docs/{doc.id}",
        json={"version": archived["version"], "archived_at": None},
    )
    assert restored.status_code == 200
    assert restored.json()["archived_at"] is None
