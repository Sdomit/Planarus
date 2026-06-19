from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    """Return (workspace_id, project_id)."""
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-ph"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-ph"},
    ).json()
    return ws["id"], proj["id"]


def test_list_phases_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/phases")
    assert res.status_code == 200
    assert res.json() == []


def test_create_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/phases",
        json={"title": "Phase 1", "status": "planned"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Phase 1"
    assert data["status"] == "planned"
    assert data["project_id"] == pid
    assert data["id"].startswith("ph_")
    assert "sort_order" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_phase_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/phases",
        json={"title": "X"},
    )
    assert res.status_code == 404


def test_create_phase_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/phases",
        json={"title": "Bad", "status": "invalid_status"},
    )
    assert res.status_code == 422


def test_update_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    ph = client.post(
        f"/api/v1/projects/{pid}/phases", json={"title": "Old"}
    ).json()
    res = client.patch(f"/api/v1/phases/{ph['id']}", json={"title": "New", "status": "active"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["status"] == "active"


def test_update_phase_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/phases/ph_doesnotexist", json={"title": "X"})
    assert res.status_code == 404


def test_sort_order_auto_assigned(client: TestClient) -> None:
    _, pid = _seed(client)
    ph1 = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "A"}).json()
    ph2 = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "B"}).json()
    assert ph2["sort_order"] > ph1["sort_order"]


def test_list_phases_ordered(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Z", "sort_order": 10})
    client.post(f"/api/v1/projects/{pid}/phases", json={"title": "A", "sort_order": 1})
    phases = client.get(f"/api/v1/projects/{pid}/phases").json()
    assert phases[0]["title"] == "A"
    assert phases[1]["title"] == "Z"


def test_create_phase_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Audit Phase"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "phase",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


def test_update_phase_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    ph = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "T"}).json()
    client.patch(f"/api/v1/phases/{ph['id']}", json={"status": "active"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "phase",
                AuditEvent.event_type == "update",
            )
        ).all()
    )
    assert len(events) == 1
