from fastapi.testclient import TestClient


def test_list_workspaces_empty(client: TestClient) -> None:
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    assert response.json() == []


def test_create_workspace(client: TestClient) -> None:
    payload = {"name": "My Workspace", "slug": "my-workspace"}
    response = client.post("/api/v1/workspaces", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Workspace"
    assert data["slug"] == "my-workspace"
    assert data["id"].startswith("ws_")
    assert "created_at" in data
    assert "updated_at" in data


def test_list_workspaces_returns_created(client: TestClient) -> None:
    client.post("/api/v1/workspaces", json={"name": "WS One", "slug": "ws-one"})
    client.post("/api/v1/workspaces", json={"name": "WS Two", "slug": "ws-two"})
    response = client.get("/api/v1/workspaces")
    assert response.status_code == 200
    slugs = [w["slug"] for w in response.json()]
    assert "ws-one" in slugs
    assert "ws-two" in slugs


def test_create_workspace_invalid_slug(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces", json={"name": "Bad", "slug": "-bad-slug-"}
    )
    assert response.status_code == 422


def test_create_workspace_slug_too_short(client: TestClient) -> None:
    response = client.post(
        "/api/v1/workspaces", json={"name": "Short", "slug": "a"}
    )
    assert response.status_code == 422


def test_create_workspace_duplicate_slug_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/workspaces", json={"name": "First", "slug": "dup-ws"}
    )
    assert first.status_code == 201
    second = client.post(
        "/api/v1/workspaces", json={"name": "Second", "slug": "dup-ws"}
    )
    assert second.status_code == 409
    assert "detail" in second.json()
