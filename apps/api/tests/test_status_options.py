"""Phase 15.5 — custom statuses / board columns."""
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-so"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-so"},
    ).json()
    return proj["id"]


def test_list_returns_builtins_by_default(client: TestClient) -> None:
    pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/status-options?entity_type=task")
    assert res.status_code == 200
    opts = res.json()
    keys = [o["key"] for o in opts]
    assert keys == ["backlog", "ready", "in_progress", "waiting", "needs_review", "blocked", "done", "canceled"]
    assert all(o["builtin"] for o in opts)
    assert all(o["id"] is None for o in opts)


def test_create_custom_status_and_use_it(client: TestClient) -> None:
    pid = _seed(client)
    made = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "In Review", "color": "#8b5cf6"},
    )
    assert made.status_code == 201
    opt = made.json()
    assert opt["key"] == "in_review" and opt["label"] == "In Review" and not opt["builtin"]

    # It now appears in the merged list after the built-ins.
    keys = [o["key"] for o in client.get(f"/api/v1/projects/{pid}/status-options").json()]
    assert keys[-1] == "in_review"

    # And a task can take it.
    tk = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "in_review"})
    assert tk.status_code == 201
    assert tk.json()["status"] == "in_review"


def test_task_rejects_undefined_status(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "nonesuch"})
    assert res.status_code == 422


def test_task_rejects_non_slug_status(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "In Review"})
    assert res.status_code == 422


def test_duplicate_custom_status_rejected(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"})
    dup = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "in review"})
    assert dup.status_code == 422


def test_cannot_shadow_builtin(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "blocked"})
    assert res.status_code == 422


def test_delete_unused_custom_status(client: TestClient) -> None:
    pid = _seed(client)
    opt = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"}).json()
    assert client.delete(f"/api/v1/status-options/{opt['id']}").status_code == 204


def test_cannot_delete_status_in_use(client: TestClient) -> None:
    pid = _seed(client)
    opt = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"}).json()
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "in_review"})
    res = client.delete(f"/api/v1/status-options/{opt['id']}")
    assert res.status_code == 409


def test_status_option_audit_written(client: TestClient, session) -> None:
    from sqlmodel import select

    from app.models.audit_event import AuditEvent

    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "status_option", AuditEvent.event_type == "create"
            )
        ).all()
    )
    assert len(events) == 1
