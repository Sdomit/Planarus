"""Phase 15.0 — delete + reorder endpoints for planning entities."""
from fastapi.testclient import TestClient
from sqlmodel import select

from app.models.audit_event import AuditEvent


def _seed(client: TestClient) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-dr"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-dr"},
    ).json()
    return proj["id"]


# --- deletes ------------------------------------------------------------------

def test_delete_milestone(client: TestClient) -> None:
    pid = _seed(client)
    m = client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "M"}).json()
    assert client.delete(f"/api/v1/milestones/{m['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/milestones").json() == []


def test_delete_missing_returns_404(client: TestClient) -> None:
    assert client.delete("/api/v1/milestones/mil_nope").status_code == 404
    assert client.delete("/api/v1/decisions/dec_nope").status_code == 404
    assert client.delete("/api/v1/risks/rsk_nope").status_code == 404
    assert client.delete("/api/v1/phases/ph_nope").status_code == 404
    assert client.delete("/api/v1/tasks/tsk_nope").status_code == 404
    assert client.delete("/api/v1/blockers/blk_nope").status_code == 404


def test_delete_decision_and_risk(client: TestClient) -> None:
    pid = _seed(client)
    d = client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "x"}).json()
    r = client.post(f"/api/v1/projects/{pid}/risks", json={"title": "R", "severity": "high"}).json()
    assert client.delete(f"/api/v1/decisions/{d['id']}").status_code == 204
    assert client.delete(f"/api/v1/risks/{r['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/decisions").json() == []
    assert client.get(f"/api/v1/projects/{pid}/risks").json() == []


def test_delete_phase_unphases_tasks_and_drops_stages(client: TestClient) -> None:
    pid = _seed(client)
    ph = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph"}).json()
    stage = client.post(
        f"/api/v1/projects/{pid}/stages", json={"title": "St", "phase_id": ph["id"]}
    ).json()
    task = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "T", "phase_id": ph["id"], "stage_id": stage["id"]},
    ).json()
    ms = client.post(
        f"/api/v1/projects/{pid}/milestones", json={"title": "M", "phase_id": ph["id"]}
    ).json()

    assert client.delete(f"/api/v1/phases/{ph['id']}").status_code == 204

    # Phase + its stage are gone; the task survives, unphased; milestone unlinked.
    assert client.get(f"/api/v1/projects/{pid}/phases").json() == []
    assert client.get(f"/api/v1/projects/{pid}/stages").json() == []
    tasks = client.get(f"/api/v1/projects/{pid}/tasks").json()
    assert len(tasks) == 1 and tasks[0]["id"] == task["id"]
    assert tasks[0]["phase_id"] is None and tasks[0]["stage_id"] is None
    mils = client.get(f"/api/v1/projects/{pid}/milestones").json()
    assert mils[0]["id"] == ms["id"] and mils[0]["phase_id"] is None


def test_delete_task_removes_checklist_and_unlinks_blocker(client: TestClient, session) -> None:
    pid = _seed(client)
    task = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    client.post(f"/api/v1/tasks/{task['id']}/checklist-items", json={"label": "step"})
    blk = client.post(
        f"/api/v1/projects/{pid}/blockers", json={"title": "B", "task_id": task["id"]}
    ).json()

    assert client.delete(f"/api/v1/tasks/{task['id']}").status_code == 204

    assert client.get(f"/api/v1/projects/{pid}/tasks").json() == []
    assert client.get(f"/api/v1/tasks/{task['id']}/checklist-items").status_code in (200, 404)
    blockers = client.get(f"/api/v1/projects/{pid}/blockers").json()
    assert len(blockers) == 1 and blockers[0]["id"] == blk["id"]
    assert blockers[0]["task_id"] is None


def test_delete_writes_audit_event(client: TestClient, session) -> None:
    pid = _seed(client)
    d = client.post(f"/api/v1/projects/{pid}/decisions", json={"title": "D", "decision": "x"}).json()
    client.delete(f"/api/v1/decisions/{d['id']}")
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "decision", AuditEvent.event_type == "delete"
            )
        ).all()
    )
    assert len(events) == 1


# --- reorder ------------------------------------------------------------------

def test_reorder_phases(client: TestClient) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/phases", json={"title": t}).json()["id"]
           for t in ("A", "B", "C")]
    reversed_ids = list(reversed(ids))
    res = client.post(f"/api/v1/projects/{pid}/phases/reorder", json={"ids": reversed_ids})
    assert res.status_code == 200
    assert [p["id"] for p in res.json()] == reversed_ids
    assert [p["sort_order"] for p in res.json()] == [0, 1, 2]
    # The GET list reflects the new order too.
    assert [p["id"] for p in client.get(f"/api/v1/projects/{pid}/phases").json()] == reversed_ids


def test_reorder_tasks(client: TestClient) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/tasks", json={"title": t}).json()["id"]
           for t in ("A", "B", "C")]
    res = client.post(f"/api/v1/projects/{pid}/tasks/reorder", json={"ids": [ids[2], ids[0], ids[1]]})
    assert res.status_code == 200
    assert [t["id"] for t in res.json()] == [ids[2], ids[0], ids[1]]


def test_reorder_rejects_incomplete_set(client: TestClient) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/phases", json={"title": t}).json()["id"]
           for t in ("A", "B")]
    # Missing one id → 422.
    assert client.post(f"/api/v1/projects/{pid}/phases/reorder", json={"ids": [ids[0]]}).status_code == 422
    # Foreign / unknown id → 422.
    assert client.post(
        f"/api/v1/projects/{pid}/phases/reorder", json={"ids": [ids[0], ids[1], "ph_foreign"]}
    ).status_code == 422


def test_reorder_decisions(client: TestClient) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/decisions", json={"title": t, "decision": "x"}).json()["id"]
           for t in ("A", "B", "C")]
    res = client.post(f"/api/v1/projects/{pid}/decisions/reorder", json={"ids": list(reversed(ids))})
    assert res.status_code == 200
    assert [d["id"] for d in res.json()] == list(reversed(ids))
    assert [d["sort_order"] for d in res.json()] == [0, 1, 2]


def test_reorder_risks(client: TestClient) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/risks", json={"title": t, "severity": "high"}).json()["id"]
           for t in ("A", "B", "C")]
    res = client.post(f"/api/v1/projects/{pid}/risks/reorder", json={"ids": [ids[1], ids[2], ids[0]]})
    assert res.status_code == 200
    # Manual order overrides the default severity ordering.
    assert [r["id"] for r in res.json()] == [ids[1], ids[2], ids[0]]


def test_reorder_project_not_found(client: TestClient) -> None:
    assert client.post("/api/v1/projects/proj_nope/phases/reorder", json={"ids": ["ph_x"]}).status_code == 404


def test_reorder_writes_single_audit_event(client: TestClient, session) -> None:
    pid = _seed(client)
    ids = [client.post(f"/api/v1/projects/{pid}/milestones", json={"title": t}).json()["id"]
           for t in ("A", "B")]
    client.post(f"/api/v1/projects/{pid}/milestones/reorder", json={"ids": list(reversed(ids))})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "milestone", AuditEvent.event_type == "reorder"
            )
        ).all()
    )
    assert len(events) == 1


def test_delete_phase_unlinks_decisions_and_risks(client: TestClient) -> None:
    """Phase 19: decisions/risks gained phase_id, so delete_phase must clear it.
    Miss them and the enforced FK makes the phase permanently undeletable."""
    pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "P1"}).json()
    dec = client.post(
        f"/api/v1/projects/{pid}/decisions",
        json={"title": "D", "decision": "X", "phase_id": phase["id"]},
    ).json()
    risk = client.post(
        f"/api/v1/projects/{pid}/risks",
        json={"title": "R", "severity": "high", "phase_id": phase["id"]},
    ).json()

    assert client.delete(f"/api/v1/phases/{phase['id']}").status_code == 204

    # Both survive the phase, unphased rather than deleted or dangling.
    decisions = client.get(f"/api/v1/projects/{pid}/decisions").json()
    risks = client.get(f"/api/v1/projects/{pid}/risks").json()
    assert [(d["id"], d["phase_id"]) for d in decisions] == [(dec["id"], None)]
    assert [(r["id"], r["phase_id"]) for r in risks] == [(risk["id"], None)]
