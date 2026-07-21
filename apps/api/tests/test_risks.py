from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-rsk"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-rsk"},
    ).json()
    return ws["id"], proj["id"]


def test_list_risks_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/risks")
    assert res.status_code == 200
    assert res.json() == []


def test_create_risk(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "Data loss", "severity": "high"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Data loss"
    assert data["severity"] == "high"
    assert data["status"] == "open"
    assert data["project_id"] == pid
    assert data["id"].startswith("rsk_")
    assert data["mitigation"] is None


def test_create_risk_with_all_fields(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={
            "title": "Perf risk",
            "severity": "critical",
            "status": "monitoring",
            "mitigation": "Add indexes",
            "description": "Slow queries",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["severity"] == "critical"
    assert data["mitigation"] == "Add indexes"


def test_create_risk_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/risks",
        json={"title": "X", "severity": "low"},
    )
    assert res.status_code == 404


def test_create_risk_missing_severity(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/risks", json={"title": "X"})
    assert res.status_code == 422


def test_create_risk_invalid_severity(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/risks", json={"title": "X", "severity": "extreme"}
    )
    assert res.status_code == 422


def test_create_risk_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "X", "severity": "low", "status": "bad"},
    )
    assert res.status_code == 422


def test_update_risk(client: TestClient) -> None:
    _, pid = _seed(client)
    risk = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "R", "severity": "low"},
    ).json()
    res = client.patch(
        f"/api/v1/risks/{risk['id']}",
        json={"status": "mitigated", "mitigation": "Fixed"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "mitigated"
    assert data["mitigation"] == "Fixed"


def test_update_risk_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/risks/rsk_doesnotexist", json={"status": "closed"})
    assert res.status_code == 404


def test_list_risks_ordered_by_severity(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/risks", json={"title": "Low", "severity": "low"})
    client.post(f"/api/v1/projects/{pid}/risks", json={"title": "Crit", "severity": "critical"})
    client.post(f"/api/v1/projects/{pid}/risks", json={"title": "High", "severity": "high"})
    risks = client.get(f"/api/v1/projects/{pid}/risks").json()
    severities = [r["severity"] for r in risks]
    assert severities == ["critical", "high", "low"]


def test_create_risk_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "medium"}
    )
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "risk",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


# --- Phase 19 (D45): optional phase link ------------------------------------


def test_create_risk_with_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    res = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "R", "severity": "high", "phase_id": phase["id"]},
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] == phase["id"]


def test_create_risk_without_phase_is_unphased(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "low"}
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] is None


def test_create_risk_rejects_phase_from_another_project(client: TestClient) -> None:
    ws_id, pid = _seed(client)
    other = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Other", "slug": "p-rsk-other"},
    ).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/phases", json={"title": "Foreign"}
    ).json()
    res = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "R", "severity": "high", "phase_id": foreign["id"]},
    )
    assert res.status_code == 404


def test_update_risk_sets_and_clears_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    risk = client.post(
        f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "medium"}
    ).json()

    linked = client.patch(f"/api/v1/risks/{risk['id']}", json={"phase_id": phase["id"]})
    assert linked.status_code == 200
    assert linked.json()["phase_id"] == phase["id"]

    cleared = client.patch(f"/api/v1/risks/{risk['id']}", json={"phase_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["phase_id"] is None


def test_update_risk_rejects_foreign_phase(client: TestClient) -> None:
    ws_id, pid = _seed(client)
    other = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_id, "title": "Other", "slug": "p-rsk-other2"},
    ).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/phases", json={"title": "Foreign"}
    ).json()
    risk = client.post(
        f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "low"}
    ).json()
    res = client.patch(f"/api/v1/risks/{risk['id']}", json={"phase_id": foreign["id"]})
    assert res.status_code == 404
