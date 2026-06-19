from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-blk"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-blk"},
    ).json()
    return ws["id"], proj["id"]


def test_list_blockers_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/blockers")
    assert res.status_code == 200
    assert res.json() == []


def test_create_blocker_no_task(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/blockers",
        json={"title": "Blocked on infra"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Blocked on infra"
    assert data["status"] == "open"
    assert data["task_id"] is None
    assert data["project_id"] == pid
    assert data["id"].startswith("blk_")


def test_create_blocker_with_task(client: TestClient) -> None:
    _, pid = _seed(client)
    task = client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Task A"}
    ).json()
    res = client.post(
        f"/api/v1/projects/{pid}/blockers",
        json={"title": "Blocker for task", "task_id": task["id"]},
    )
    assert res.status_code == 201
    assert res.json()["task_id"] == task["id"]


def test_create_blocker_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/blockers",
        json={"title": "X"},
    )
    assert res.status_code == 404


def test_create_blocker_task_not_found(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/blockers",
        json={"title": "X", "task_id": "tsk_doesnotexist"},
    )
    assert res.status_code == 404


def test_create_blocker_task_project_mismatch(client: TestClient) -> None:
    """Task belonging to a different project must return 404."""
    ws2 = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-blk2"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2["id"], "title": "P2", "slug": "p-blk2"},
    ).json()
    _, pid = _seed(client)
    task = client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Task A"}
    ).json()
    res = client.post(
        f"/api/v1/projects/{proj2['id']}/blockers",
        json={"title": "X", "task_id": task["id"]},
    )
    assert res.status_code == 404


def test_create_blocker_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/blockers",
        json={"title": "X", "status": "bad"},
    )
    assert res.status_code == 422


def test_update_blocker(client: TestClient) -> None:
    _, pid = _seed(client)
    blk = client.post(
        f"/api/v1/projects/{pid}/blockers", json={"title": "Old"}
    ).json()
    res = client.patch(
        f"/api/v1/blockers/{blk['id']}",
        json={"title": "New", "status": "resolved"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["status"] == "resolved"


def test_update_blocker_not_found(client: TestClient) -> None:
    res = client.patch(
        "/api/v1/blockers/blk_doesnotexist", json={"status": "resolved"}
    )
    assert res.status_code == 404


def test_create_blocker_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/blockers", json={"title": "B"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "blocker",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


# --- update parent integrity tests ---


def test_update_blocker_cross_project_task(client: TestClient) -> None:
    """PATCH blocker to a task from another project returns 404."""
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task A"}).json()
    ws2 = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-blk-xt"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2["id"], "title": "P2", "slug": "p-blk-xt"},
    ).json()
    blk = client.post(
        f"/api/v1/projects/{proj2['id']}/blockers", json={"title": "B"}
    ).json()
    # task belongs to pid, blk belongs to proj2 — mismatch
    res = client.patch(f"/api/v1/blockers/{blk['id']}", json={"task_id": task["id"]})
    assert res.status_code == 404


def test_update_blocker_nonexistent_task(client: TestClient) -> None:
    """PATCH blocker to a nonexistent task returns 404."""
    _, pid = _seed(client)
    blk = client.post(f"/api/v1/projects/{pid}/blockers", json={"title": "B"}).json()
    res = client.patch(f"/api/v1/blockers/{blk['id']}", json={"task_id": "tsk_doesnotexist"})
    assert res.status_code == 404


def test_update_blocker_valid_task_reassign(client: TestClient) -> None:
    """PATCH blocker to a different same-project task succeeds."""
    _, pid = _seed(client)
    task1 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task 1"}).json()
    task2 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Task 2"}).json()
    blk = client.post(
        f"/api/v1/projects/{pid}/blockers",
        json={"title": "B", "task_id": task1["id"]},
    ).json()
    res = client.patch(f"/api/v1/blockers/{blk['id']}", json={"task_id": task2["id"]})
    assert res.status_code == 200
    assert res.json()["task_id"] == task2["id"]
