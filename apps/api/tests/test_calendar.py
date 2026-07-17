from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-cf"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": "p-cf"},
    ).json()
    return ws["id"], proj["id"]


def test_calendar_unions_events_milestones_tasks(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Kickoff", "start_at": "2026-08-10T10:00:00+00:00"},
    )
    client.post(
        f"/api/v1/projects/{pid}/milestones",
        json={"title": "Beta", "target_date": "2026-08-15"},
    )
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Ship docs", "due_at": "2026-08-12"},
    )
    # Milestone without a date and task without a due date are excluded.
    client.post(f"/api/v1/projects/{pid}/milestones", json={"title": "NoDate"})
    client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "NoDue"})

    res = client.get(f"/api/v1/projects/{pid}/calendar")
    assert res.status_code == 200
    body = res.json()
    sources = sorted(item["source"] for item in body["items"])
    assert sources == ["event", "milestone", "task"]
    # Sorted by start_at ascending.
    starts = [item["start_at"][:10] for item in body["items"]]
    assert starts == sorted(starts)


def test_calendar_range_filter(client: TestClient) -> None:
    _, pid = _seed(client)
    for day in ("2026-07-01", "2026-08-15", "2026-09-30"):
        client.post(
            f"/api/v1/projects/{pid}/milestones",
            json={"title": f"M {day}", "target_date": day},
        )
    res = client.get(
        f"/api/v1/projects/{pid}/calendar", params={"from": "2026-08-01", "to": "2026-08-31"}
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["start_at"] == "2026-08-15"


def test_calendar_project_not_found(client: TestClient) -> None:
    res = client.get("/api/v1/projects/proj_nope/calendar")
    assert res.status_code == 404
