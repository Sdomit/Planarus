"""Phase 9 roadmap rollups."""
from fastapi.testclient import TestClient


def _seed(client: TestClient, suffix: str = "rdm") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "Road", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


def test_roadmap_empty_project(client: TestClient) -> None:
    pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/roadmap")
    assert res.status_code == 200
    data = res.json()
    assert data["phases"] == []
    assert data["totals"] == {"total": 0, "done": 0, "in_progress": 0, "blocked": 0}
    assert data["pct_done"] == 0


def test_roadmap_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/projects/proj_nope/roadmap").status_code == 404


def test_roadmap_rollups(client: TestClient) -> None:
    pid = _seed(client)
    phase = client.post(
        f"/api/v1/projects/{pid}/phases", json={"title": "Phase A"}
    ).json()
    stage = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"title": "Stage S", "phase_id": phase["id"]},
    ).json()

    def mk(title: str, status: str, **extra) -> dict:
        return client.post(
            f"/api/v1/projects/{pid}/tasks",
            json={"title": title, "status": status, **extra},
        ).json()

    # In the stage (counts in stage AND phase): done.
    mk("t1", "done", stage_id=stage["id"])
    # Attached to the phase directly: in_progress + blocked.
    mk("t2", "in_progress", phase_id=phase["id"])
    mk("t5", "blocked", phase_id=phase["id"])
    # Canceled is excluded everywhere.
    mk("t4", "canceled", phase_id=phase["id"])
    # Unphased.
    mk("t3", "backlog")

    data = client.get(f"/api/v1/projects/{pid}/roadmap").json()
    assert len(data["phases"]) == 1
    p = data["phases"][0]
    assert p["tasks"] == {"total": 3, "done": 1, "in_progress": 1, "blocked": 1}
    assert p["pct_done"] == 33
    assert len(p["stages"]) == 1
    s = p["stages"][0]
    assert s["tasks"] == {"total": 1, "done": 1, "in_progress": 0, "blocked": 0}
    assert s["pct_done"] == 100
    assert data["unphased"] == {"total": 1, "done": 0, "in_progress": 0, "blocked": 0}
    assert data["totals"]["total"] == 4
    assert data["pct_done"] == 25


def test_roadmap_task_in_stage_counts_in_parent_phase(client: TestClient) -> None:
    """A task holding only stage_id still rolls up to the stage's phase."""
    pid = _seed(client, suffix="rdm2")
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "PhX"}).json()
    stage = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"title": "StX", "phase_id": phase["id"]},
    ).json()
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "only-stage", "status": "done", "stage_id": stage["id"]},
    )
    data = client.get(f"/api/v1/projects/{pid}/roadmap").json()
    assert data["phases"][0]["tasks"]["total"] == 1
    assert data["unphased"]["total"] == 0
