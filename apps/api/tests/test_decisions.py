from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-dec"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-dec"},
    ).json()
    return ws["id"], proj["id"]


def test_list_decisions_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/decisions")
    assert res.status_code == 200
    assert res.json() == []


def test_create_decision(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "Use SQLite", "decision": "SQLite for local-first MVP"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Use SQLite"
    assert data["decision"] == "SQLite for local-first MVP"
    assert data["status"] == "proposed"
    assert data["project_id"] == pid
    assert data["id"].startswith("dec_")
    assert data["context"] is None


def test_create_decision_with_context(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={
            "title": "Use SQLite",
            "decision": "SQLite",
            "context": "Need local-first",
            "status": "accepted",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["context"] == "Need local-first"
    assert data["status"] == "accepted"


def test_create_decision_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/decisions",
        json={"title": "X", "decision": "Y"},
    )
    assert res.status_code == 404


def test_create_decision_missing_decision_field(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "X"},
    )
    assert res.status_code == 422


def test_create_decision_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "X", "decision": "Y", "status": "bad"},
    )
    assert res.status_code == 422


def test_update_decision(client: TestClient) -> None:
    _, pid = _seed(client)
    dec = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "T", "decision": "D"},
    ).json()
    res = client.patch(
        f"/api/v1/decisions/{dec['id']}",
        json={"status": "accepted", "decision": "Updated D"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "accepted"
    assert data["decision"] == "Updated D"


def test_update_decision_not_found(client: TestClient) -> None:
    res = client.patch(
        "/api/v1/decisions/dec_doesnotexist", json={"status": "accepted"}
    )
    assert res.status_code == 404


def test_list_decisions_newest_first(client: TestClient) -> None:
    """Decisions should be returned newest-first (created_at desc)."""
    import time
    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "First", "decision": "A"})
    time.sleep(0.01)
    client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "Second", "decision": "B"})
    decisions = client.get(f"/api/v1/projects/{pid}/decisions").json()
    assert len(decisions) == 2
    assert decisions[0]["title"] == "Second"


def test_create_decision_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "Decided"},
    )
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "decision",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


# --- Phase 19 (D45): optional phase link ------------------------------------


def test_create_decision_with_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "Decided", "phase_id": phase["id"]},
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] == phase["id"]


def test_create_decision_without_phase_is_unphased(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "X"}
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] is None


def test_create_decision_rejects_phase_from_another_project(client: TestClient) -> None:
    ws_id, pid = _seed(client)
    other = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Other", "slug": "p-dec-other"},
    ).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/phases", json={"title": "Foreign"}
    ).json()
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "X", "phase_id": foreign["id"]},
    )
    assert res.status_code == 404


def test_create_decision_rejects_missing_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "X", "phase_id": "pha_nope"},
    )
    assert res.status_code == 404


def test_update_decision_sets_and_clears_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    dec = client.post(
        f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "X"}
    ).json()

    linked = client.patch(
        f"/api/v1/decisions/{dec['id']}", json={"phase_id": phase["id"]}
    )
    assert linked.status_code == 200
    assert linked.json()["phase_id"] == phase["id"]

    cleared = client.patch(f"/api/v1/decisions/{dec['id']}", json={"phase_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["phase_id"] is None


def test_update_decision_rejects_foreign_phase(client: TestClient) -> None:
    ws_id, pid = _seed(client)
    other = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Other", "slug": "p-dec-other2"},
    ).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/phases", json={"title": "Foreign"}
    ).json()
    dec = client.post(
        f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "X"}
    ).json()
    res = client.patch(
        f"/api/v1/decisions/{dec['id']}", json={"phase_id": foreign["id"]}
    )
    assert res.status_code == 404
