"""Phase 15.7 — editable, triageable comments."""
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-ce"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-ce"},
    ).json()
    return proj["id"]


def _comment(client: TestClient, pid: str) -> dict:
    return client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "Hello"},
    ).json()


def test_new_comment_defaults_to_active(client: TestClient) -> None:
    pid = _seed(client)
    c = _comment(client, pid)
    assert c["status"] == "active"
    assert c["updated_at"] is None


def test_edit_comment_body_and_status(client: TestClient) -> None:
    pid = _seed(client)
    c = _comment(client, pid)
    res = client.patch(f"/api/v1/comments/{c['id']}", json={"body": "Edited", "status": "done"})
    assert res.status_code == 200
    data = res.json()
    assert data["body"] == "Edited"
    assert data["status"] == "done"
    assert data["updated_at"] is not None


def test_edit_comment_invalid_status(client: TestClient) -> None:
    pid = _seed(client)
    c = _comment(client, pid)
    assert client.patch(f"/api/v1/comments/{c['id']}", json={"status": "bogus"}).status_code == 422


def test_edit_comment_not_found(client: TestClient) -> None:
    assert client.patch("/api/v1/comments/cmt_nope", json={"status": "done"}).status_code == 404


def test_delete_comment(client: TestClient) -> None:
    pid = _seed(client)
    c = _comment(client, pid)
    assert client.delete(f"/api/v1/comments/{c['id']}").status_code == 204
    remaining = client.get(f"/api/v1/projects/{pid}/comments").json()
    assert all(x["id"] != c["id"] for x in remaining)


def test_edit_comment_writes_audit(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    pid = _seed(client)
    c = _comment(client, pid)
    client.patch(f"/api/v1/comments/{c['id']}", json={"status": "attention"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "comment", AuditEvent.event_type == "update"
            )
        ).all()
    )
    assert len(events) == 1
