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


def test_custom_phase_status(client: TestClient) -> None:
    pid = _seed(client)
    opts = client.get(f"/api/v1/projects/{pid}/status-options?entity_type=phase").json()
    assert [o["key"] for o in opts] == ["planned", "active", "blocked", "done", "canceled"]
    made = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "phase", "label": "On Hold"},
    ).json()
    assert made["key"] == "on_hold"
    ph = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "P", "status": "on_hold"})
    assert ph.status_code == 201 and ph.json()["status"] == "on_hold"
    # An undefined phase status is rejected.
    assert client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Q", "status": "nope"}).status_code == 422


def test_custom_risk_status_keeps_severity_strict(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "risk", "label": "Watching"})
    rk = client.post(f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "high", "status": "watching"})
    assert rk.status_code == 201 and rk.json()["status"] == "watching"
    # Severity is still a fixed enum.
    assert client.post(f"/api/v1/projects/{pid}/risks", json={"title": "R2", "severity": "spicy"}).status_code == 422
    # Undefined risk status rejected.
    assert client.post(f"/api/v1/projects/{pid}/risks", json={"title": "R3", "severity": "low", "status": "bogus"}).status_code == 422


def test_custom_milestone_status(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "milestone", "label": "At Risk"})
    m = client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "M", "status": "at_risk"})
    assert m.status_code == 201 and m.json()["status"] == "at_risk"
    assert client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "M2", "status": "bogus"}).status_code == 422


def test_custom_decision_status(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "decision", "label": "Deferred"})
    d = client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "x", "status": "deferred"})
    assert d.status_code == 201 and d.json()["status"] == "deferred"
    assert client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "D2", "decision": "y", "status": "bogus"}).status_code == 422


def test_status_options_are_per_entity_type(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "phase", "label": "On Hold"})
    # The phase custom status is not offered for tasks.
    task_keys = [o["key"] for o in client.get(f"/api/v1/projects/{pid}/status-options?entity_type=task").json()]
    assert "on_hold" not in task_keys
    assert client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "on_hold"}).status_code == 422


def test_rename_custom_status_keeps_key(client: TestClient) -> None:
    pid = _seed(client)
    opt = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "In Review"},
    ).json()
    # A task already using the status.
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T", "status": "in_review"})
    res = client.patch(f"/api/v1/status-options/{opt['id']}", json={"label": "Under Review"})
    assert res.status_code == 200
    body = res.json()
    # Label changes but the slug key is stable, so existing cards keep working.
    assert body["label"] == "Under Review" and body["key"] == "in_review"


def test_recolor_custom_status(client: TestClient) -> None:
    pid = _seed(client)
    opt = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "In Review"},
    ).json()
    res = client.patch(f"/api/v1/status-options/{opt['id']}", json={"color": "#8B5CF6"})
    assert res.status_code == 200 and res.json()["color"] == "#8b5cf6"
    # Clearing color is allowed.
    cleared = client.patch(f"/api/v1/status-options/{opt['id']}", json={"color": ""})
    assert cleared.status_code == 200 and cleared.json()["color"] is None


def test_reject_bad_color(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "In Review", "color": "purple"},
    )
    assert res.status_code == 422


def test_update_missing_status_option_404(client: TestClient) -> None:
    _seed(client)
    assert client.patch("/api/v1/status-options/sto_nope", json={"label": "X"}).status_code == 404


def test_reorder_custom_statuses(client: TestClient) -> None:
    pid = _seed(client)
    a = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"}).json()
    b = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "On Hold"}).json()
    c = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "Verifying"}).json()
    # Default order is creation order after the built-ins.
    keys = [o["key"] for o in client.get(f"/api/v1/projects/{pid}/status-options").json() if not o["builtin"]]
    assert keys == ["in_review", "on_hold", "verifying"]
    res = client.post(
        f"/api/v1/projects/{pid}/status-options/reorder?entity_type=task",
        json={"ids": [c["id"], a["id"], b["id"]]},
    )
    assert res.status_code == 200
    reordered = [o["key"] for o in res.json() if not o["builtin"]]
    assert reordered == ["verifying", "in_review", "on_hold"]
    # Built-ins still lead.
    assert res.json()[0]["key"] == "backlog"


def test_reorder_rejects_incomplete_id_set(client: TestClient) -> None:
    pid = _seed(client)
    a = client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "In Review"}).json()
    client.post(f"/api/v1/projects/{pid}/status-options", json={"entity_type": "task", "label": "On Hold"})
    res = client.post(
        f"/api/v1/projects/{pid}/status-options/reorder?entity_type=task",
        json={"ids": [a["id"]]},
    )
    assert res.status_code == 422


def test_status_option_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

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
