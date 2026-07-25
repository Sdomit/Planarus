"""Same-project parent invariant for documents (#116).

`parent_doc_id` was assigned straight from the payload. The self-FK proves the id
exists globally, not that it belongs to the same project, so a workspace editor
could parent a project-A doc to a project-B one — and deleting the project-B
parent then cleared the project-A child's `parent_doc_id` and bumped its
`updated_at`, a write across the tenant boundary inside the victim's transaction.
"""
import pytest
from app.core.hierarchy import MAX_DEPTH, validate_parent
from app.models.doc import Doc
from app.services import doc_service


@pytest.fixture(name="two_projects")
def two_projects_fixture(client):
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "wdp"}).json()["id"]
    a = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "A", "slug": "dpa"}
    ).json()["id"]
    b = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "B", "slug": "dpb"}
    ).json()["id"]
    return a, b


def _doc(client, project_id, title, **body):
    r = client.post(
        f"/api/v1/projects/{project_id}/docs",
        json={"title": title, "doc_type": "note", **body},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_same_project_parent_is_accepted(client, two_projects):
    a, _ = two_projects
    parent = _doc(client, a, "Parent")
    child = _doc(client, a, "Child", parent_doc_id=parent["id"])
    assert child["parent_doc_id"] == parent["id"]


def test_cross_project_parent_is_rejected_on_create(client, two_projects, session):
    a, b = two_projects
    foreign = _doc(client, b, "Foreign")
    r = client.post(
        f"/api/v1/projects/{a}/docs", json={"title": "C", "doc_type": "note", "parent_doc_id": foreign["id"]}
    )
    assert r.status_code == 422, r.text
    assert not session.exec(
        Doc.__table__.select().where(Doc.__table__.c.title == "C")
    ).all(), "rejected create still wrote a row"


def test_cross_project_parent_is_rejected_on_update(client, two_projects):
    a, b = two_projects
    foreign = _doc(client, b, "Foreign")
    child = _doc(client, a, "Child")
    r = client.patch(
        f"/api/v1/docs/{child['id']}",
        json={"parent_doc_id": foreign["id"], "version": child["version"]},
    )
    assert r.status_code == 422, r.text
    assert client.get(f"/api/v1/docs/{child['id']}").json()["parent_doc_id"] is None


def test_missing_parent_is_rejected(client, two_projects):
    a, _ = two_projects
    r = client.post(
        f"/api/v1/projects/{a}/docs", json={"title": "C", "doc_type": "note", "parent_doc_id": "doc-nope"}
    )
    assert r.status_code == 422, r.text


def test_a_cross_project_parent_is_indistinguishable_from_a_missing_one(client, two_projects):
    """Probing ids across projects must not reveal which ones exist."""
    a, b = two_projects
    foreign = _doc(client, b, "Foreign")
    cross = client.post(
        f"/api/v1/projects/{a}/docs", json={"title": "X", "doc_type": "note", "parent_doc_id": foreign["id"]}
    )
    missing = client.post(
        f"/api/v1/projects/{a}/docs", json={"title": "Y", "doc_type": "note", "parent_doc_id": "doc-nope"}
    )
    assert cross.status_code == missing.status_code == 422
    assert cross.json()["detail"].replace(foreign["id"], "ID") == missing.json()[
        "detail"
    ].replace("doc-nope", "ID")


def test_self_parent_is_rejected(client, two_projects):
    a, _ = two_projects
    doc = _doc(client, a, "Solo")
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"parent_doc_id": doc["id"], "version": doc["version"]},
    )
    assert r.status_code == 422
    assert "itself" in r.json()["detail"]


def test_multi_level_cycle_is_rejected(client, two_projects):
    """a -> b -> c, then pointing a's parent at c would close the loop."""
    a, _ = two_projects
    top = _doc(client, a, "Top")
    mid = _doc(client, a, "Mid", parent_doc_id=top["id"])
    leaf = _doc(client, a, "Leaf", parent_doc_id=mid["id"])
    r = client.patch(
        f"/api/v1/docs/{top['id']}",
        json={"parent_doc_id": leaf["id"], "version": top["version"]},
    )
    assert r.status_code == 422
    assert "cycle" in r.json()["detail"]


def test_delete_never_touches_another_projects_document(client, two_projects, session):
    """The pre-#116 leak, reproduced through the data layer since the API can no
    longer create the row: deleting B's parent must not edit A's child."""
    a, b = two_projects
    parent = _doc(client, b, "B parent")
    child = _doc(client, a, "A child")

    victim = session.get(Doc, child["id"])
    victim.parent_doc_id = parent["id"]  # legacy row, written before the guard
    session.add(victim)
    session.commit()
    before = victim.updated_at

    assert client.delete(f"/api/v1/docs/{parent['id']}").status_code == 204

    session.expire_all()
    after = session.get(Doc, child["id"])
    assert after is not None, "the other project's document was deleted"
    assert after.updated_at == before, "delete bumped another project's updated_at"
    # The pointer is cleared because the self-FK cannot hold a dangling id — but
    # that is the only trace the delete may leave.
    assert after.parent_doc_id is None


def test_repair_reports_then_clears_legacy_rows(client, two_projects, session):
    a, b = two_projects
    foreign = _doc(client, b, "Foreign")
    child = _doc(client, a, "Child")
    selfie = _doc(client, a, "Selfie")

    for doc_id, parent_id in ((child["id"], foreign["id"]), (selfie["id"], selfie["id"])):
        row = session.get(Doc, doc_id)
        row.parent_doc_id = parent_id
        session.add(row)
    session.commit()

    dry = doc_service.repair_parent_integrity(session, dry_run=True)
    assert {f["reason"] for f in dry} == {"parent in another project", "self-parent"}
    session.expire_all()
    assert session.get(Doc, child["id"]).parent_doc_id == foreign["id"], "dry run wrote"

    fixed = doc_service.repair_parent_integrity(session)
    assert len(fixed) == 2
    session.expire_all()
    assert session.get(Doc, child["id"]).parent_doc_id is None
    assert session.get(Doc, selfie["id"]).parent_doc_id is None
    assert doc_service.repair_parent_integrity(session) == [], "not idempotent"


def test_repair_survives_a_pre_existing_cycle(client, two_projects, session):
    """A cycle already in the data must be reported, not spin the walk forever."""
    a, _ = two_projects
    one = _doc(client, a, "One")
    two = _doc(client, a, "Two", parent_doc_id=one["id"])
    row = session.get(Doc, one["id"])
    row.parent_doc_id = two["id"]
    session.add(row)
    session.commit()

    findings = doc_service.repair_parent_integrity(session)
    assert [f["reason"] for f in findings] == ["cycle"] * len(findings)
    assert findings, "the cycle was not detected"
    assert doc_service.repair_parent_integrity(session) == []


def test_validate_parent_is_generic_over_the_parent_attribute(session, client, two_projects):
    """The helper exists for phases/tasks/connections too, not just Doc."""
    a, _ = two_projects
    parent = _doc(client, a, "P")
    assert (
        validate_parent(
            session,
            Doc,
            parent_id=parent["id"],
            project_id=a,
            parent_attr="parent_doc_id",
        )
        == parent["id"]
    )
    assert validate_parent(session, Doc, parent_id=None, project_id=a) is None
    assert MAX_DEPTH >= 8, "a doc tree should be allowed to be a few levels deep"


def test_duplicate_preserves_hierarchy_within_the_copy(client, two_projects, session):
    """#87's graph registry remaps parent_doc_id; prove the copy is self-contained."""
    a, _ = two_projects
    parent = _doc(client, a, "Parent")
    _doc(client, a, "Child", parent_doc_id=parent["id"])

    r = client.post(f"/api/v1/projects/{a}/duplicate", json={"title": "Copy", "slug": "dpcopy"})
    assert r.status_code in (200, 201), r.text
    copy_id = r.json()["id"]

    copies = session.exec(Doc.__table__.select().where(Doc.__table__.c.project_id == copy_id)).all()
    by_id = {row.id: row for row in copies}
    assert by_id, "duplicate produced no docs"
    for row in copies:
        if row.parent_doc_id is not None:
            assert row.parent_doc_id in by_id, "copied doc still points at the original project"
