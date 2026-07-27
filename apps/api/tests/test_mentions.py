"""Backend tests for @mention backlinks, derived from a doc's content_json (#138/plan 23)."""
import json

import pytest
from fastapi.testclient import TestClient

_EMPTY_JSON = '{"type": "doc", "content": [{"type": "paragraph"}]}'


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-men"}).json()
    proj = client.post(
        "/api/v1/projects", json={"workspace_id": ws["id"], "title": "P", "slug": "p-men"}
    ).json()
    return ws["id"], proj["id"]


def _task(client: TestClient, project_id: str, title: str = "T") -> dict:
    r = client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _doc(client: TestClient, project_id: str, title: str = "D") -> dict:
    r = client.post(f"/api/v1/projects/{project_id}/docs", json={"title": title, "doc_type": "note"})
    assert r.status_code == 201, r.text
    return r.json()


def _mention_node(target_type: str, target_id: str, label: str = "ref") -> dict:
    return {"type": "mention", "attrs": {"targetType": target_type, "targetId": target_id, "label": label}}


def _content_with_mentions(*nodes: dict) -> str:
    return json.dumps(
        {"type": "doc", "content": [{"type": "paragraph", "content": [n]} for n in nodes]}
    )


def _save_content(client: TestClient, doc: dict, content_json: str) -> dict:
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": doc["version"], "content_json": content_json, "markdown_cache": ""},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_saving_two_mentions_creates_two_rows(client: TestClient) -> None:
    _, pid = _seed(client)
    t1, t2 = _task(client, pid, "T1"), _task(client, pid, "T2")
    doc = _doc(client, pid)
    _save_content(
        client, doc,
        _content_with_mentions(_mention_node("task", t1["id"]), _mention_node("task", t2["id"])),
    )

    res = client.get(f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]})
    assert res.status_code == 200
    assert {m["target_id"] for m in res.json()} == {t1["id"], t2["id"]}


def test_resaving_with_fewer_mentions_drops_the_removed_rows(client: TestClient) -> None:
    _, pid = _seed(client)
    t1, t2 = _task(client, pid, "T1"), _task(client, pid, "T2")
    doc = _doc(client, pid)
    doc = _save_content(
        client, doc,
        _content_with_mentions(_mention_node("task", t1["id"]), _mention_node("task", t2["id"])),
    )
    doc = _save_content(client, doc, _content_with_mentions(_mention_node("task", t1["id"])))

    res = client.get(f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]})
    assert [m["target_id"] for m in res.json()] == [t1["id"]]


def test_mention_targeting_a_nonexistent_entity_is_skipped(client: TestClient) -> None:
    _, pid = _seed(client)
    doc = _doc(client, pid)
    _save_content(client, doc, _content_with_mentions(_mention_node("task", "task-nope")))

    res = client.get(f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]})
    assert res.json() == []


def test_mention_targeting_another_projects_entity_is_skipped(client: TestClient) -> None:
    _, pid_a = _seed(client)
    ws = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-men-b"}).json()
    pid_b = client.post(
        "/api/v1/projects", json={"workspace_id": ws["id"], "title": "B", "slug": "p-men-b"}
    ).json()["id"]
    foreign_task = _task(client, pid_b, "Foreign")
    doc = _doc(client, pid_a)
    _save_content(client, doc, _content_with_mentions(_mention_node("task", foreign_task["id"])))

    res = client.get(f"/api/v1/projects/{pid_a}/mentions", params={"source_doc_id": doc["id"]})
    assert res.json() == []


@pytest.mark.parametrize(
    "attrs",
    [
        pytest.param({"targetType": "task"}, id="dict-missing-targetId"),
        pytest.param({}, id="empty-dict"),
        pytest.param(None, id="null"),
        # The four that used to 500: `attrs or {}` rescued falsy values only, so
        # any truthy non-dict reached .get() and raised AttributeError out of the
        # save — losing the user's edit, and recurring on every subsequent save
        # once such a node had been stored by an import or an approved patch.
        pytest.param(["oops"], id="list"),
        pytest.param("oops", id="string"),
        pytest.param(5, id="number"),
        pytest.param(True, id="bool"),
        pytest.param([[{"targetType": "task", "targetId": "x"}]], id="nested-list"),
        # Right shape, wrong value types.
        pytest.param({"targetType": "task", "targetId": 123}, id="non-str-id"),
        pytest.param({"targetType": ["task"], "targetId": "x"}, id="non-str-type"),
        pytest.param({"targetType": "", "targetId": ""}, id="empty-strings"),
    ],
)
def test_malformed_mention_attrs_are_skipped_not_crashed(client: TestClient, attrs) -> None:
    """The doc schema bounds size/depth/node-count but never node *shape*."""
    _, pid = _seed(client)
    doc = _doc(client, pid)
    bad = {"type": "mention", "attrs": attrs}
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={
            "version": doc["version"],
            "content_json": json.dumps({"type": "doc", "content": [{"type": "paragraph", "content": [bad]}]}),
            "markdown_cache": "",
        },
    )
    assert r.status_code == 200, r.text
    assert client.get(f"/api/v1/projects/{pid}/mentions").json() == []


def test_a_stored_malformed_mention_does_not_wedge_later_saves(client: TestClient, session) -> None:
    """The sticky half of the bug: paths that write content_json *without* going
    through update_doc (import, approval-apply) can store a malformed node, and
    every later human save then had to survive parsing it."""
    from app.models.doc import Doc

    _, pid = _seed(client)
    doc = _doc(client, pid)
    row = session.get(Doc, doc["id"])
    row.content_json = json.dumps(
        {"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "mention", "attrs": ["planted out of band"]},
        ]}]}
    )
    session.add(row)
    session.commit()

    fresh = client.get(f"/api/v1/docs/{doc['id']}").json()
    r = client.patch(
        f"/api/v1/docs/{doc['id']}",
        json={"version": fresh["version"], "content_json": _EMPTY_JSON, "markdown_cache": ""},
    )
    assert r.status_code == 200, r.text


def test_a_metadata_only_save_does_not_touch_mentions(client: TestClient) -> None:
    _, pid = _seed(client)
    t1 = _task(client, pid, "T1")
    doc = _doc(client, pid)
    doc = _save_content(client, doc, _content_with_mentions(_mention_node("task", t1["id"])))

    r = client.patch(f"/api/v1/docs/{doc['id']}", json={"version": doc["version"], "title": "Renamed"})
    assert r.status_code == 200, r.text

    res = client.get(f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]})
    assert [m["target_id"] for m in res.json()] == [t1["id"]]


def test_backlinks_endpoint_finds_the_referencing_doc(client: TestClient) -> None:
    _, pid = _seed(client)
    t1 = _task(client, pid, "T1")
    doc = _doc(client, pid, "Referencer")
    _save_content(client, doc, _content_with_mentions(_mention_node("task", t1["id"])))

    res = client.get(
        f"/api/v1/projects/{pid}/mentions", params={"target_type": "task", "target_id": t1["id"]}
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 1
    assert rows[0]["source_doc_id"] == doc["id"]
    assert rows[0]["target_type"] == "task"
    assert rows[0]["id"].startswith("men_")
    assert rows[0]["source_doc_title"] == "Referencer"


def test_deleting_the_source_doc_deletes_its_mention_rows(client: TestClient) -> None:
    _, pid = _seed(client)
    t1 = _task(client, pid, "T1")
    doc = _doc(client, pid)
    _save_content(client, doc, _content_with_mentions(_mention_node("task", t1["id"])))

    res = client.delete(f"/api/v1/docs/{doc['id']}")
    assert res.status_code == 204, res.text

    res = client.get(
        f"/api/v1/projects/{pid}/mentions", params={"target_type": "task", "target_id": t1["id"]}
    )
    assert res.json() == []


def test_the_approval_apply_path_re_derives_mentions(client: TestClient, session) -> None:
    """`policy.handlers._apply_doc_update` writes content_json directly rather
    than through `update_doc`, so it has to re-derive the projection itself.
    Without that, an approved agent edit left the backlink table describing the
    *previous* content."""
    from app.policy.handlers import apply_action

    _, pid = _seed(client)
    keep, added = _task(client, pid, "Keep"), _task(client, pid, "Added")
    doc = _doc(client, pid)
    _save_content(client, doc, _content_with_mentions(_mention_node("task", keep["id"])))
    assert [m["target_id"] for m in client.get(
        f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]}
    ).json()] == [keep["id"]]

    # An approved edit that drops the old mention and introduces a different one.
    apply_action(
        session,
        action_type="doc.update",
        project_id=pid,
        target_entity_id=doc["id"],
        patch={
            "content_json": _content_with_mentions(_mention_node("task", added["id"])),
            "markdown_cache": "",
        },
    )
    session.commit()

    rows = client.get(
        f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]}
    ).json()
    assert [m["target_id"] for m in rows] == [added["id"]], "approved edit left stale backlinks"


def test_many_mentions_cost_a_bounded_number_of_queries(client: TestClient, session) -> None:
    """Guards the save-time amplification: validating N references must not be N
    round-trips. `session.get` does not cache a miss, so fabricated ids used to
    cost exactly as much as real ones — 30k of them inside the open write
    transaction of a single 2 MB PATCH."""
    from sqlalchemy import event

    _, pid = _seed(client)
    real = _task(client, pid, "Real")
    doc = _doc(client, pid)

    # One resolvable target plus a flood of fabricated ones across two types.
    nodes = (
        [_mention_node("task", real["id"])]
        + [_mention_node("task", f"tsk_fake{i}") for i in range(800)]
        + [_mention_node("decision", f"dec_fake{i}") for i in range(800)]
    )

    engine = session.get_bind()
    selects: list[str] = []

    def _count(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", _count)
    try:
        _save_content(client, doc, _content_with_mentions(*nodes))
    finally:
        event.remove(engine, "before_cursor_execute", _count)

    # Only the resolvable target survives; 1600 fabricated ids are dropped.
    rows = client.get(
        f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]}
    ).json()
    assert [m["target_id"] for m in rows] == [real["id"]]

    # The whole PATCH — doc fetch, CAS, existing-row sweep, audit, plus mention
    # validation — stays far below one-query-per-reference. Generous bound: the
    # point is 1601 references cost tens of queries, not ~1601.
    assert len(selects) < 60, f"{len(selects)} SELECTs for 1601 references"


def test_mention_rows_per_doc_are_capped(client: TestClient) -> None:
    from app.services.mention_service import MAX_MENTIONS_PER_DOC

    _, pid = _seed(client)
    doc = _doc(client, pid)
    tasks = [_task(client, pid, f"T{i}") for i in range(5)]
    _save_content(
        client, doc, _content_with_mentions(*[_mention_node("task", t["id"]) for t in tasks])
    )
    rows = client.get(
        f"/api/v1/projects/{pid}/mentions", params={"source_doc_id": doc["id"]}
    ).json()
    assert len(rows) == 5
    assert len(rows) <= MAX_MENTIONS_PER_DOC
