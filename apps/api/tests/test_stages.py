from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str, str]:
    """Return (workspace_id, project_id, phase_id)."""
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-stg"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-stg"},
    ).json()
    ph = client.post(
        f"/api/v1/projects/{proj['id']}/phases", json={"title": "Ph1"}
    ).json()
    return ws["id"], proj["id"], ph["id"]


def test_list_stages_empty(client: TestClient) -> None:
    _, pid, _ = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/stages")
    assert res.status_code == 200
    assert res.json() == []


def test_create_stage(client: TestClient) -> None:
    _, pid, ph_id = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"phase_id": ph_id, "title": "Stage 1"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Stage 1"
    assert data["phase_id"] == ph_id
    assert data["project_id"] == pid
    assert data["id"].startswith("stg_")


def test_create_stage_project_not_found(client: TestClient) -> None:
    _, _, ph_id = _seed(client)
    res = client.post(
        "/api/v1/projects/proj_doesnotexist/stages",
        json={"phase_id": ph_id, "title": "X"},
    )
    assert res.status_code == 404


def test_create_stage_phase_not_found(client: TestClient) -> None:
    _, pid, _ = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"phase_id": "ph_doesnotexist", "title": "X"},
    )
    assert res.status_code == 404


def test_create_stage_phase_project_mismatch(client: TestClient) -> None:
    """Phase belonging to a different project must return 404."""
    ws = client.post("/api/v1/workspaces", json={"name": "WS2", "slug": "ws-stg2"}).json()
    proj2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P2", "slug": "p-stg2"},
    ).json()
    _, pid, ph_id = _seed(client)
    res = client.post(
        f"/api/v1/projects/{proj2['id']}/stages",
        json={"phase_id": ph_id, "title": "X"},
    )
    assert res.status_code == 404


def test_create_stage_invalid_status(client: TestClient) -> None:
    _, pid, ph_id = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"phase_id": ph_id, "title": "X", "status": "bad"},
    )
    assert res.status_code == 422


def test_update_stage(client: TestClient) -> None:
    _, pid, ph_id = _seed(client)
    stg = client.post(
        f"/api/v1/projects/{pid}/stages",
        json={"phase_id": ph_id, "title": "Old"},
    ).json()
    res = client.patch(f"/api/v1/stages/{stg['id']}", json={"title": "New", "status": "active"})
    assert res.status_code == 200
    assert res.json()["title"] == "New"
    assert res.json()["status"] == "active"


def test_update_stage_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/stages/stg_doesnotexist", json={"title": "X"})
    assert res.status_code == 404


def test_list_stages_by_project(client: TestClient) -> None:
    _, pid, ph_id = _seed(client)
    client.post(f"/api/v1/projects/{pid}/stages", json={"phase_id": ph_id, "title": "S1"})
    client.post(f"/api/v1/projects/{pid}/stages", json={"phase_id": ph_id, "title": "S2"})
    stages = client.get(f"/api/v1/projects/{pid}/stages").json()
    assert len(stages) == 2


def test_sort_order_auto_assigned(client: TestClient) -> None:
    _, pid, ph_id = _seed(client)
    s1 = client.post(
        f"/api/v1/projects/{pid}/stages", json={"phase_id": ph_id, "title": "A"}
    ).json()
    s2 = client.post(
        f"/api/v1/projects/{pid}/stages", json={"phase_id": ph_id, "title": "B"}
    ).json()
    assert s2["sort_order"] > s1["sort_order"]
