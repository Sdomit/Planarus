from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-tsk"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-tsk"},
    ).json()
    return ws["id"], proj["id"]


def test_list_tasks_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/tasks")
    assert res.status_code == 200
    assert res.json() == []


def test_create_task(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "My task", "status": "backlog"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "My task"
    assert data["status"] == "backlog"
    assert data["project_id"] == pid
    assert data["id"].startswith("tsk_")
    assert data["phase_id"] is None
    assert data["stage_id"] is None


def test_create_task_with_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    ph = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph"}).json()
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Task with phase", "phase_id": ph["id"]},
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] == ph["id"]


def test_create_task_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/tasks",
        json={"title": "X"},
    )
    assert res.status_code == 404


def test_create_task_phase_not_found(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "X", "phase_id": "ph_doesnotexist"},
    )
    assert res.status_code == 404


def test_create_task_stage_not_found(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "X", "stage_id": "stg_doesnotexist"},
    )
    assert res.status_code == 404


def test_create_task_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "X", "status": "invalid"},
    )
    assert res.status_code == 422


def test_create_task_invalid_priority(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "X", "priority": "extreme"},
    )
    assert res.status_code == 422


def test_update_task(client: TestClient) -> None:
    _, pid = _seed(client)
    task = client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Old"}
    ).json()
    res = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"title": "New", "status": "in_progress", "priority": "high"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["status"] == "in_progress"
    assert data["priority"] == "high"


def test_update_task_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/tasks/tsk_doesnotexist", json={"title": "X"})
    assert res.status_code == 404


def test_sort_order_auto_assigned(client: TestClient) -> None:
    _, pid = _seed(client)
    t1 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "A"}).json()
    t2 = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "B"}).json()
    assert t2["sort_order"] > t1["sort_order"]


def test_create_task_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Audit Task"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "task",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


def test_update_task_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    client.patch(f"/api/v1/tasks/{task['id']}", json={"status": "done"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "task",
                AuditEvent.event_type == "update",
            )
        ).all()
    )
    assert len(events) == 1


# --- update parent integrity tests ---


def test_update_task_cross_project_phase(client: TestClient) -> None:
    """PATCH task to a phase from another project returns 404."""
    ws2 = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-tsk-xp2"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2["id"], "title": "P2", "slug": "p-tsk-xp2"},
    ).json()
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    ph2 = client.post(f"/api/v1/projects/{proj2['id']}/phases", json={"title": "Ph2"}).json()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"phase_id": ph2["id"]})
    assert res.status_code == 404


def test_update_task_cross_project_stage(client: TestClient) -> None:
    """PATCH task to a stage from another project returns 404."""
    ws2 = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-tsk-xs2"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2["id"], "title": "P2", "slug": "p-tsk-xs2"},
    ).json()
    ph2 = client.post(
        f"/api/v1/projects/{proj2['id']}/phases", json={"title": "Ph2"}
    ).json()
    stg2 = client.post(
        f"/api/v1/projects/{proj2['id']}/stages",
        json={"title": "Stg2", "phase_id": ph2["id"]},
    ).json()
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"stage_id": stg2["id"]})
    assert res.status_code == 404


def test_update_task_nonexistent_phase(client: TestClient) -> None:
    """PATCH task to a nonexistent phase returns 404."""
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"phase_id": "ph_doesnotexist"})
    assert res.status_code == 404


def test_update_task_nonexistent_stage(client: TestClient) -> None:
    """PATCH task to a nonexistent stage returns 404."""
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"stage_id": "stg_doesnotexist"})
    assert res.status_code == 404


def test_update_task_phase_stage_mismatch(client: TestClient) -> None:
    """PATCH task with stage from a different phase than the supplied phase_id returns 422."""
    _, pid = _seed(client)
    ph1 = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    ph2 = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph2"}).json()
    stg1 = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"title": "Stg1", "phase_id": ph1["id"]},
    ).json()
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    # stg1 belongs to ph1 but we pass ph2 — mismatch
    res = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"phase_id": ph2["id"], "stage_id": stg1["id"]},
    )
    assert res.status_code == 422


def test_update_task_valid_reparent(client: TestClient) -> None:
    """PATCH task to a same-project phase/stage succeeds."""
    _, pid = _seed(client)
    ph = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph"}).json()
    stg = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"title": "Stg", "phase_id": ph["id"]},
    ).json()
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    res = client.patch(
        f"/api/v1/tasks/{task['id']}",
        json={"phase_id": ph["id"], "stage_id": stg["id"]},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["phase_id"] == ph["id"]
    assert data["stage_id"] == stg["id"]
