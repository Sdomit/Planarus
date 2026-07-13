from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-cmt"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-cmt"},
    ).json()
    return ws["id"], proj["id"]


def test_list_comments_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/comments")
    assert res.status_code == 200
    assert res.json() == []


def test_create_project_comment(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "Kickoff note"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["body"] == "Kickoff note"
    assert data["entity_type"] == "project"
    assert data["author_type"] == "human"
    assert data["id"].startswith("cmt_")


def test_create_comment_on_task(client: TestClient) -> None:
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "task", "entity_id": task["id"], "body": "on task"},
    )
    assert res.status_code == 201


def test_list_comments_filter_by_entity(client: TestClient) -> None:
    _, pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "proj"},
    )
    client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "task", "entity_id": task["id"], "body": "task"},
    )
    res = client.get(
        f"/api/v1/projects/{pid}/comments",
        params={"entity_type": "task", "entity_id": task["id"]},
    )
    assert res.status_code == 200
    bodies = [c["body"] for c in res.json()]
    assert bodies == ["task"]


def test_create_comment_invalid_entity_type(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "banana", "entity_id": pid, "body": "x"},
    )
    assert res.status_code == 422


def test_create_comment_empty_body(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": ""},
    )
    assert res.status_code == 422


def test_create_comment_entity_not_in_project(client: TestClient) -> None:
    """A task from another project must be rejected as a comment target."""
    _, pid = _seed(client)
    ws2 = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-cmt2"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws2["id"], "title": "P2", "slug": "p-cmt2"},
    ).json()
    task2 = client.post(
        f"/api/v1/projects/{proj2['id']}/tasks", json={"title": "T2"}
    ).json()
    res = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "task", "entity_id": task2["id"], "body": "x"},
    )
    assert res.status_code == 404


def test_create_comment_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_nope/comments",
        json={"entity_type": "project", "entity_id": "proj_nope", "body": "x"},
    )
    assert res.status_code == 404


def test_create_comment_audit_written(client: TestClient, session) -> None:
    from sqlmodel import select

    from app.models.audit_event import AuditEvent

    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "x"},
    )
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "comment",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1
