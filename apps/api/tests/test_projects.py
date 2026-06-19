from fastapi.testclient import TestClient


def _create_workspace(client: TestClient, slug: str = "test-ws") -> str:
    res = client.post("/api/v1/workspaces", json={"name": "Test WS", "slug": slug})
    assert res.status_code == 201
    return res.json()["id"]


def test_list_projects_empty(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    assert response.json() == []


def test_create_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    payload = {
        "workspace_id": ws_id,
        "title": "My Project",
        "slug": "my-project",
        "status": "planning",
    }
    response = client.post("/api/v1/projects", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My Project"
    assert data["slug"] == "my-project"
    assert data["status"] == "planning"
    assert data["id"].startswith("proj_")
    assert data["workspace_id"] == ws_id
    assert "created_at" in data
    assert "updated_at" in data


def test_get_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    created = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Get Me", "slug": "get-me"},
    ).json()
    response = client.get(f"/api/v1/projects/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_project_not_found(client: TestClient) -> None:
    response = client.get("/api/v1/projects/proj_doesnotexist")
    assert response.status_code == 404


def test_update_project(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    created = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Old Title", "slug": "old-title"},
    ).json()
    response = client.patch(
        f"/api/v1/projects/{created['id']}",
        json={"title": "New Title", "status": "active"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Title"
    assert data["status"] == "active"


def test_update_project_not_found(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/projects/proj_doesnotexist",
        json={"title": "New"},
    )
    assert response.status_code == 404


def test_list_projects_by_workspace(client: TestClient) -> None:
    ws1 = _create_workspace(client, "workspace-one")
    ws2 = _create_workspace(client, "workspace-two")
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws1, "title": "P1", "slug": "p-one"},
    )
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2, "title": "P2", "slug": "p-two"},
    )
    res1 = client.get(f"/api/v1/projects?workspace_id={ws1}").json()
    res2 = client.get(f"/api/v1/projects?workspace_id={ws2}").json()
    assert len(res1) == 1 and res1[0]["slug"] == "p-one"
    assert len(res2) == 1 and res2[0]["slug"] == "p-two"


def test_create_project_invalid_status(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "X", "slug": "xx", "status": "invalid"},
    )
    assert response.status_code == 422


def test_create_project_invalid_slug(client: TestClient) -> None:
    ws_id = _create_workspace(client)
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "X", "slug": "-bad-"},
    )
    assert response.status_code == 422


def test_create_project_missing_workspace(client: TestClient) -> None:
    response = client.post(
        "/api/v1/projects",
        json={"workspace_id": "ws_nonexistent", "title": "X", "slug": "xx"},
    )
    assert response.status_code == 404


def test_audit_event_created_on_project_create(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    ws_id = _create_workspace(client)
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Audited", "slug": "audited"},
    )
    events = session.exec(
        select(AuditEvent).where(AuditEvent.event_type == "create")
    ).all()
    # workspace create + project create = 2 events
    project_events = [e for e in events if e.entity_type == "project"]
    assert len(project_events) == 1
    assert project_events[0].actor_type == "human"
