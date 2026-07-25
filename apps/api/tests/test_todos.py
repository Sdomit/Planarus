"""Project-scoped sidebar todos: CRUD, arbitrary nesting, re-parent guards,
subtree delete."""
from fastapi.testclient import TestClient


def _seed(client: TestClient, suffix: str = "todo") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def _add(client: TestClient, pid: str, label: str, parent_id: str | None = None) -> dict:
    body: dict = {"label": label}
    if parent_id is not None:
        body["parent_id"] = parent_id
    res = client.post(f"/api/v1/projects/{pid}/todos", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_and_list(client: TestClient) -> None:
    pid = _seed(client)
    assert client.get(f"/api/v1/projects/{pid}/todos").json() == []
    a = _add(client, pid, "buy milk")
    assert a["parent_id"] is None and a["done"] is False and a["id"].startswith("td_")
    _add(client, pid, "walk dog")
    got = client.get(f"/api/v1/projects/{pid}/todos").json()
    assert [t["label"] for t in got] == ["buy milk", "walk dog"]
    assert [t["sort_order"] for t in got] == [0, 1]


def test_arbitrary_nesting(client: TestClient) -> None:
    """sub → sub-sub → sub-sub-sub, all via parent_id."""
    pid = _seed(client)
    top = _add(client, pid, "top")
    sub = _add(client, pid, "sub", parent_id=top["id"])
    subsub = _add(client, pid, "sub-sub", parent_id=sub["id"])
    subsubsub = _add(client, pid, "sub-sub-sub", parent_id=subsub["id"])
    assert subsub["parent_id"] == sub["id"]
    assert subsubsub["parent_id"] == subsub["id"]
    assert len(client.get(f"/api/v1/projects/{pid}/todos").json()) == 4


def test_toggle_done_and_rename(client: TestClient) -> None:
    pid = _seed(client)
    t = _add(client, pid, "task")
    r = client.patch(f"/api/v1/todos/{t['id']}", json={"done": True})
    assert r.status_code == 200 and r.json()["done"] is True
    r = client.patch(f"/api/v1/todos/{t['id']}", json={"label": "renamed"})
    assert r.json()["label"] == "renamed" and r.json()["done"] is True  # done preserved


def test_reparent_and_outdent(client: TestClient) -> None:
    pid = _seed(client)
    a = _add(client, pid, "a")
    b = _add(client, pid, "b")
    # nest b under a
    assert client.patch(f"/api/v1/todos/{b['id']}", json={"parent_id": a["id"]}).json()["parent_id"] == a["id"]
    # outdent b back to top (explicit null)
    assert client.patch(f"/api/v1/todos/{b['id']}", json={"parent_id": None}).json()["parent_id"] is None


def test_reparent_under_own_descendant_rejected(client: TestClient) -> None:
    pid = _seed(client)
    a = _add(client, pid, "a")
    child = _add(client, pid, "child", parent_id=a["id"])
    # moving a under its own child would create a cycle
    r = client.patch(f"/api/v1/todos/{a['id']}", json={"parent_id": child["id"]})
    assert r.status_code == 400
    # and a todo cannot be its own parent
    assert client.patch(f"/api/v1/todos/{a['id']}", json={"parent_id": a["id"]}).status_code == 400


def test_parent_in_other_project_rejected(client: TestClient) -> None:
    pid = _seed(client, "t1")
    other = _seed(client, "t2")
    foreign = _add(client, other, "foreign")
    res = client.post(f"/api/v1/projects/{pid}/todos", json={"label": "x", "parent_id": foreign["id"]})
    assert res.status_code == 404


def test_delete_cascades_subtree(client: TestClient) -> None:
    pid = _seed(client)
    top = _add(client, pid, "top")
    sub = _add(client, pid, "sub", parent_id=top["id"])
    _add(client, pid, "sub-sub", parent_id=sub["id"])
    sibling = _add(client, pid, "sibling")
    assert client.delete(f"/api/v1/todos/{top['id']}").status_code == 204
    remaining = client.get(f"/api/v1/projects/{pid}/todos").json()
    assert [t["id"] for t in remaining] == [sibling["id"]]  # whole subtree gone


def test_delete_missing_404(client: TestClient) -> None:
    _seed(client)
    assert client.delete("/api/v1/todos/td_missing").status_code == 404


def test_create_under_missing_parent_404(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/todos", json={"label": "x", "parent_id": "td_nope"})
    assert res.status_code == 404
