"""Phase 15.8 — sub-tasks (parent_task_id, one level deep)."""
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-st"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-st"},
    ).json()
    return proj["id"]


def _task(client: TestClient, pid: str, title: str, parent: str | None = None):
    body = {"title": title}
    if parent:
        body["parent_task_id"] = parent
    return client.post(f"/api/v1/projects/{pid}/tasks", json=body)


def test_create_subtask(client: TestClient) -> None:
    pid = _seed(client)
    parent = _task(client, pid, "Parent").json()
    res = _task(client, pid, "Child", parent["id"])
    assert res.status_code == 201
    assert res.json()["parent_task_id"] == parent["id"]


def test_subtask_parent_not_found(client: TestClient) -> None:
    pid = _seed(client)
    assert _task(client, pid, "Child", "tsk_nope").status_code == 404


def test_no_two_level_nesting(client: TestClient) -> None:
    pid = _seed(client)
    parent = _task(client, pid, "Parent").json()
    child = _task(client, pid, "Child", parent["id"]).json()
    # A grandchild (parent already has a parent) is rejected.
    assert _task(client, pid, "Grandchild", child["id"]).status_code == 422


def test_cannot_self_parent(client: TestClient) -> None:
    pid = _seed(client)
    t = _task(client, pid, "T").json()
    assert client.patch(f"/api/v1/tasks/{t['id']}", json={"parent_task_id": t["id"]}).status_code == 422


def test_reparent_via_update(client: TestClient) -> None:
    pid = _seed(client)
    p1 = _task(client, pid, "P1").json()
    child = _task(client, pid, "Child", p1["id"]).json()
    p2 = _task(client, pid, "P2").json()
    res = client.patch(f"/api/v1/tasks/{child['id']}", json={"parent_task_id": p2["id"]})
    assert res.status_code == 200
    assert res.json()["parent_task_id"] == p2["id"]


def test_deleting_parent_promotes_children(client: TestClient) -> None:
    pid = _seed(client)
    parent = _task(client, pid, "Parent").json()
    child = _task(client, pid, "Child", parent["id"]).json()
    assert client.delete(f"/api/v1/tasks/{parent['id']}").status_code == 204
    tasks = {t["id"]: t for t in client.get(f"/api/v1/projects/{pid}/tasks").json()}
    assert parent["id"] not in tasks
    assert tasks[child["id"]]["parent_task_id"] is None
