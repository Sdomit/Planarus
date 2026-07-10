"""Phase 9 AgentRun CRUD + analytics."""
from fastapi.testclient import TestClient


def _seed(client: TestClient, suffix: str = "run") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def test_list_agent_runs_empty(client: TestClient) -> None:
    pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/agent-runs")
    assert res.status_code == 200
    assert res.json() == []


def test_create_agent_run_defaults(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/agent-runs", json={})
    assert res.status_code == 201
    data = res.json()
    assert data["id"].startswith("run_")
    assert data["agent_family"] == "unspecified"
    assert data["status"] == "started"
    assert data["started_at"]
    assert data["ended_at"] is None


def test_create_agent_run_full(client: TestClient) -> None:
    pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={
            "agent_family": "claude",
            "agent_name": "claude-fable-5",
            "mode": "implement",
            "status": "succeeded",
            "summary": "Implemented phase 9",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["agent_family"] == "claude"
    assert data["mode"] == "implement"
    # terminal status without an explicit ended_at → service stamps one
    assert data["ended_at"] is not None


def test_create_agent_run_validation(client: TestClient) -> None:
    pid = _seed(client)
    assert (
        client.post(
            f"/api/v1/projects/{pid}/agent-runs", json={"agent_family": "skynet"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{pid}/agent-runs", json={"status": "exploded"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{pid}/agent-runs", json={"mode": "vibe"}
        ).status_code
        == 422
    )
    # timestamps must be ISO-8601 — garbage would silently corrupt analytics
    assert (
        client.post(
            f"/api/v1/projects/{pid}/agent-runs", json={"started_at": "yesterday"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/projects/{pid}/agent-runs", json={"ended_at": "07/10/2026"}
        ).status_code
        == 422
    )


def test_create_agent_run_project_not_found(client: TestClient) -> None:
    res = client.post("/api/v1/projects/proj_nope/agent-runs", json={})
    assert res.status_code == 404


def test_list_agent_runs_newest_first(client: TestClient) -> None:
    pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={"started_at": "2026-07-01T10:00:00+00:00"},
    )
    client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={"started_at": "2026-07-02T10:00:00+00:00"},
    )
    runs = client.get(f"/api/v1/projects/{pid}/agent-runs").json()
    assert [r["started_at"] for r in runs] == [
        "2026-07-02T10:00:00+00:00",
        "2026-07-01T10:00:00+00:00",
    ]


def test_update_agent_run_terminal_sets_ended_at(client: TestClient) -> None:
    pid = _seed(client)
    run = client.post(f"/api/v1/projects/{pid}/agent-runs", json={}).json()
    assert run["ended_at"] is None
    res = client.patch(
        f"/api/v1/agent-runs/{run['id']}",
        json={"status": "succeeded", "summary": "done"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "succeeded"
    assert data["summary"] == "done"
    assert data["ended_at"] is not None

    # Reopening clears the stale end time — a running run has no ended_at.
    reopened = client.patch(
        f"/api/v1/agent-runs/{run['id']}", json={"status": "started"}
    ).json()
    assert reopened["ended_at"] is None


def test_update_agent_run_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/agent-runs/run_nope", json={"status": "failed"})
    assert res.status_code == 404


def test_analytics_empty(client: TestClient) -> None:
    pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/agent-runs/analytics")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["success_rate"] is None
    assert data["avg_duration_minutes"] is None
    assert data["last_run_at"] is None


def test_analytics_math(client: TestClient) -> None:
    pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={
            "agent_family": "claude",
            "mode": "implement",
            "status": "succeeded",
            "started_at": "2026-07-01T10:00:00+00:00",
            "ended_at": "2026-07-01T10:30:00+00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={
            "agent_family": "claude",
            "mode": "review",
            "status": "failed",
            "started_at": "2026-07-02T10:00:00+00:00",
            "ended_at": "2026-07-02T10:10:00+00:00",
        },
    )
    client.post(
        f"/api/v1/projects/{pid}/agent-runs",
        json={"agent_family": "codex", "started_at": "2026-07-03T09:00:00+00:00"},
    )
    data = client.get(f"/api/v1/projects/{pid}/agent-runs/analytics").json()
    assert data["total"] == 3
    assert data["by_family"] == {"claude": 2, "codex": 1}
    assert data["by_status"] == {"succeeded": 1, "failed": 1, "started": 1}
    assert data["by_mode"] == {"implement": 1, "review": 1}
    assert data["success_rate"] == 0.5
    assert data["avg_duration_minutes"] == 20.0
    assert data["last_run_at"] == "2026-07-03T09:00:00+00:00"


def test_analytics_project_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/projects/proj_nope/agent-runs/analytics")
    assert res.status_code == 404
