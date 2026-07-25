from fastapi.testclient import TestClient


def _seed_task(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-cli"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-cli"},
    ).json()
    task = client.post(
        f"/api/v1/projects/{proj['id']}/tasks", json={"title": "Task A"}
    ).json()
    return task["id"]


def test_list_checklist_empty(client: TestClient) -> None:
    tid = _seed_task(client)
    res = client.get(f"/api/v1/tasks/{tid}/checklist-items")
    assert res.status_code == 200
    assert res.json() == []


def test_create_checklist_item(client: TestClient) -> None:
    tid = _seed_task(client)
    res = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "Write tests"}
    )
    assert res.status_code == 201
    data = res.json()
    assert data["label"] == "Write tests"
    assert data["done"] is False
    assert data["sort_order"] == 0
    assert data["task_id"] == tid
    assert data["id"].startswith("cli_")


def test_checklist_sort_order_increments(client: TestClient) -> None:
    tid = _seed_task(client)
    client.post(f"/api/v1/tasks/{tid}/checklist-items", json={"label": "one"})
    second = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "two"}
    ).json()
    assert second["sort_order"] == 1


def test_create_checklist_task_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/tasks/tsk_nope/checklist-items", json={"label": "x"}
    )
    assert res.status_code == 404


def test_create_checklist_empty_label(client: TestClient) -> None:
    tid = _seed_task(client)
    res = client.post(f"/api/v1/tasks/{tid}/checklist-items", json={"label": ""})
    assert res.status_code == 422


def test_update_checklist_toggle_done(client: TestClient) -> None:
    tid = _seed_task(client)
    item = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "todo"}
    ).json()
    res = client.patch(
        f"/api/v1/checklist-items/{item['id']}", json={"done": True}
    )
    assert res.status_code == 200
    assert res.json()["done"] is True


def test_update_checklist_label(client: TestClient) -> None:
    tid = _seed_task(client)
    item = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "old"}
    ).json()
    res = client.patch(
        f"/api/v1/checklist-items/{item['id']}", json={"label": "new"}
    )
    assert res.status_code == 200
    assert res.json()["label"] == "new"


def test_update_checklist_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/checklist-items/cli_nope", json={"done": True})
    assert res.status_code == 404


def test_delete_checklist_item(client: TestClient) -> None:
    tid = _seed_task(client)
    item = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "remove me"}
    ).json()
    res = client.delete(f"/api/v1/checklist-items/{item['id']}")
    assert res.status_code == 204
    remaining = client.get(f"/api/v1/tasks/{tid}/checklist-items").json()
    assert remaining == []


def test_delete_checklist_not_found(client: TestClient) -> None:
    res = client.delete("/api/v1/checklist-items/cli_nope")
    assert res.status_code == 404


def test_sort_order_stable_after_delete(client: TestClient) -> None:
    # Deleting an item must not cause a later insert to reuse a live sort_order.
    tid = _seed_task(client)
    first = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "one"}
    ).json()
    second = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "two"}
    ).json()
    assert second["sort_order"] == 1
    client.delete(f"/api/v1/checklist-items/{first['id']}")
    third = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "three"}
    ).json()
    # max(sort_order) was 1 (the surviving "two"), so the next is 2 — no collision.
    assert third["sort_order"] == 2
    assert third["sort_order"] != second["sort_order"]


def test_delete_checklist_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    tid = _seed_task(client)
    item = client.post(
        f"/api/v1/tasks/{tid}/checklist-items", json={"label": "x"}
    ).json()
    client.delete(f"/api/v1/checklist-items/{item['id']}")
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "checklist_item",
                AuditEvent.event_type == "delete",
            )
        ).all()
    )
    assert len(events) == 1
    assert events[0].project_id is not None


def test_create_checklist_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    tid = _seed_task(client)
    client.post(f"/api/v1/tasks/{tid}/checklist-items", json={"label": "x"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "checklist_item",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1
    assert events[0].project_id is not None  # derived from the parent task
