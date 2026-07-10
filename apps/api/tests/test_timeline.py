"""Phase 9 project timeline (audit-event derived)."""
from fastapi.testclient import TestClient


def _seed(client: TestClient, suffix: str = "tml") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def test_timeline_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/proj_nope/timeline").status_code == 404


def test_timeline_events_with_resolved_titles(client: TestClient) -> None:
    pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "Fix login bug"})
    client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "Use SQLite", "decision": "SQLite in WAL mode"},
    )

    res = client.get(f"/api/v1/projects/{pid}/timeline")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == pid
    labels = [e["label"] for e in data["events"]]
    assert any("create task — Fix login bug" == lbl for lbl in labels)
    assert any("create decision — Use SQLite" == lbl for lbl in labels)
    # newest first
    ats = [e["at"] for e in data["events"]]
    assert ats == sorted(ats, reverse=True)


def test_timeline_limit(client: TestClient) -> None:
    pid = _seed(client, suffix="tml2")
    for i in range(3):
        client.post(f"/api/v1/projects/{pid}/tasks", json={"title": f"T{i}"})
    data = client.get(f"/api/v1/projects/{pid}/timeline?limit=2").json()
    assert len(data["events"]) == 2
    assert client.get(f"/api/v1/projects/{pid}/timeline?limit=0").status_code == 422
    assert client.get(f"/api/v1/projects/{pid}/timeline?limit=201").status_code == 422


def test_timeline_unresolvable_entity_keeps_generic_label(client: TestClient) -> None:
    """Events whose entity was deleted (or has no resolver) still render."""
    pid = _seed(client, suffix="tml3")
    # Project creation itself wrote an audit event with entity_type='project',
    # which has no resolver in the timeline — the generic label must appear.
    data = client.get(f"/api/v1/projects/{pid}/timeline").json()
    assert len(data["events"]) >= 1
    assert all(e["label"] for e in data["events"])
