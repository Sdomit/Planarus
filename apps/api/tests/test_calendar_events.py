from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-cal"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-cal"},
    ).json()
    return ws["id"], proj["id"]


def test_list_calendar_events_empty(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.get(f"/api/v1/projects/{pid}/calendar-events")
    assert res.status_code == 200
    assert res.json() == []


def test_create_calendar_event_minimal(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Standup", "start_at": "2026-08-03T09:00:00+00:00"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Standup"
    assert data["status"] == "confirmed"
    assert data["all_day"] is False
    assert data["start_at"] == "2026-08-03T09:00:00+00:00"
    assert data["id"].startswith("cal_")


def test_create_calendar_event_all_day_and_fields(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={
            "title": "Conf",
            "start_at": "2026-09-01",
            "end_at": "2026-09-03",
            "all_day": True,
            "status": "tentative",
            "location": "Berlin",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["all_day"] is True
    assert data["end_at"] == "2026-09-03"
    assert data["status"] == "tentative"
    assert data["location"] == "Berlin"


def test_create_calendar_event_invalid_status(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "X", "start_at": "2026-09-01", "status": "bad"},
    )
    assert res.status_code == 422


def test_create_calendar_event_phase_not_found(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "X", "start_at": "2026-09-01", "phase_id": "ph_nope"},
    )
    assert res.status_code == 404


def test_create_calendar_event_project_not_found(client: TestClient) -> None:
    res = client.post(
        "/api/v1/projects/proj_nope/calendar-events",
        json={"title": "X", "start_at": "2026-09-01"},
    )
    assert res.status_code == 404


def test_update_calendar_event(client: TestClient) -> None:
    _, pid = _seed(client)
    ev = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Old", "start_at": "2026-09-01"},
    ).json()
    res = client.patch(
        f"/api/v1/calendar-events/{ev['id']}",
        json={"title": "New", "start_at": "2026-09-05", "status": "cancelled"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["start_at"] == "2026-09-05"
    assert data["status"] == "cancelled"


def test_update_calendar_event_not_found(client: TestClient) -> None:
    res = client.patch("/api/v1/calendar-events/cal_nope", json={"title": "X"})
    assert res.status_code == 404


def test_delete_calendar_event(client: TestClient) -> None:
    _, pid = _seed(client)
    ev = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Bye", "start_at": "2026-09-01"},
    ).json()
    res = client.delete(f"/api/v1/calendar-events/{ev['id']}")
    assert res.status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/calendar-events").json() == []


def test_delete_calendar_event_not_found(client: TestClient) -> None:
    res = client.delete("/api/v1/calendar-events/cal_nope")
    assert res.status_code == 404


def test_calendar_event_audit_written(client: TestClient, session) -> None:
    from sqlmodel import select

    from app.models.audit_event import AuditEvent

    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "M", "start_at": "2026-09-01"},
    )
    events = list(
        session.exec(
            select(AuditEvent).where(
                AuditEvent.entity_type == "calendar_event",
                AuditEvent.event_type == "create",
            )
        ).all()
    )
    assert len(events) == 1
