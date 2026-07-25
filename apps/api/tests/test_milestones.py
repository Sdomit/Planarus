from types import SimpleNamespace

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-mil"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-mil"},
    ).json()
    return ws["id"], proj["id"]


def test_list_milestones_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/milestones")
    assert res.status_code == 200
    assert res.json() == []


def test_create_milestone_minimal(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "Beta"})
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Beta"
    assert data["status"] == "planned"
    assert data["target_date"] is None
    assert data["sort_order"] == 0
    assert data["id"].startswith("mil_")


def test_create_milestone_with_date_and_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/milestones",
        json={"title": "GA", "status": "active", "target_date": "2026-09-01"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == "active"
    assert data["target_date"] == "2026-09-01"


def test_create_milestone_with_phase(client: TestClient) -> None:
    _, pid = _seed(client)
    phase = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Ph1"}).json()
    res = client.post(
        f"/api/v1/projects/{pid}/milestones",
        json={"title": "M", "phase_id": phase["id"]},
    )
    assert res.status_code == 201
    assert res.json()["phase_id"] == phase["id"]


def test_create_milestone_phase_not_found(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/milestones",
        json={"title": "M", "phase_id": "ph_nope"},
    )
    assert res.status_code == 404


def test_create_milestone_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/milestones", json={"title": "M", "status": "bad"}
    )
    assert res.status_code == 422


def test_create_milestone_project_not_found(client: TestClient) -> None:
    res = client.post("/api/v1/projects/proj_nope/milestones", json={"title": "M"})
    assert res.status_code == 404


def test_update_milestone(client: TestClient) -> None:
    _, pid = _seed(client)
    mil = client.post(
        f"/api/v1/projects/{pid}/milestones", json={"title": "Old"}
    ).json()
    res = client.patch(
        f"/api/v1/milestones/{mil['id']}",
        json={"title": "New", "status": "achieved", "target_date": "2026-10-01"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["status"] == "achieved"
    assert data["target_date"] == "2026-10-01"


def test_update_milestone_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/milestones/mil_nope", json={"status": "achieved"})
    assert res.status_code == 404


def test_create_milestone_audit_written(client: TestClient, session) -> None:
    from app.models.audit_event import AuditEvent
    from sqlmodel import select

    _, pid = _seed(client)
    client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "M"})
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "milestone",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1


def test_roadmap_renderer_includes_milestones() -> None:
    """The context-pack ROADMAP body fills its Milestones section, and stays
    'None yet' when empty (keeps golden output byte-stable)."""
    from app.fsmemory.renderers import RenderContext, _roadmap_body

    m = SimpleNamespace(
        id="mil_1", title="Beta launch", status="planned",
        target_date="2026-08-01", sort_order=0,
    )
    ctx = RenderContext(
        project=SimpleNamespace(), workspace=SimpleNamespace(),
        updated_at="x", milestones=(m,),
    )
    body = "\n".join(_roadmap_body(ctx))
    assert "## Milestones" in body
    assert "Beta launch" in body
    assert "2026-08-01" in body

    empty = "\n".join(
        _roadmap_body(
            RenderContext(
                project=SimpleNamespace(), workspace=SimpleNamespace(), updated_at="x"
            )
        )
    )
    assert "_None yet._" in empty
