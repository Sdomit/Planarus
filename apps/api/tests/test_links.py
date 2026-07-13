from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-lnk"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-lnk"},
    ).json()
    return ws["id"], proj["id"]


def test_list_links_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/links")
    assert res.status_code == 200
    assert res.json() == []


def test_create_project_link(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={
            "entity_type": "project",
            "entity_id": pid,
            "url": "https://example.com/spec",
            "title": "Spec",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["url"] == "https://example.com/spec"
    assert data["title"] == "Spec"
    assert data["id"].startswith("lnk_")


def test_create_link_without_title(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "project", "entity_id": pid, "url": "https://x.dev"},
    )
    assert res.status_code == 201
    assert res.json()["title"] is None


def test_list_links_filter_by_entity(client: TestClient) -> None:
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "project", "entity_id": pid, "url": "https://p.dev"},
    )
    client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "task", "entity_id": task["id"], "url": "https://t.dev"},
    )
    res = client.get(
        f"/api/v1/projects/{pid}/links",
        params={"entity_type": "task", "entity_id": task["id"]},
    )
    assert res.status_code == 200
    urls = [link["url"] for link in res.json()]
    assert urls == ["https://t.dev"]


def test_create_link_invalid_entity_type(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "banana", "entity_id": pid, "url": "https://x.dev"},
    )
    assert res.status_code == 422


def test_create_link_rejects_javascript_scheme(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={
            "entity_type": "project",
            "entity_id": pid,
            "url": "javascript:alert(1)",
        },
    )
    assert res.status_code == 422


def test_create_link_entity_not_in_project(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "task", "entity_id": "tsk_nope", "url": "https://x.dev"},
    )
    assert res.status_code == 404


def test_create_link_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_nope/links",
        json={"entity_type": "project", "entity_id": "proj_nope", "url": "https://x.dev"},
    )
    assert res.status_code == 404


def test_create_link_audit_written(client: TestClient, session) -> None:
    from sqlmodel import select

    from app.models.audit_event import AuditEvent

    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/links",
        json={"entity_type": "project", "entity_id": pid, "url": "https://x.dev"},
    )
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "link",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1
