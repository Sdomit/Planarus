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


def test_weekly_recurrence_expands_within_range(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Standup", "start_at": "2026-08-03", "all_day": True,
              "recurrence": "weekly"},
    )
    res = client.get(
        f"/api/v1/projects/{pid}/calendar",
        params={"from": "2026-08-01", "to": "2026-08-31"},
    )
    items = res.json()["items"]
    # Aug 3, 10, 17, 24, 31 — five weekly occurrences.
    days = sorted(it["start_at"] for it in items)
    assert days == ["2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24", "2026-08-31"]
    assert all(it["recurring"] for it in items)
    # Every occurrence points back at the same underlying event.
    assert len({it["ref_id"] for it in items}) == 1


def test_recurrence_until_bounds_occurrences(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Daily", "start_at": "2026-08-01", "all_day": True,
              "recurrence": "daily", "recurrence_until": "2026-08-03"},
    )
    res = client.get(
        f"/api/v1/projects/{pid}/calendar",
        params={"from": "2026-08-01", "to": "2026-08-31"},
    )
    days = sorted(it["start_at"] for it in res.json()["items"])
    assert days == ["2026-08-01", "2026-08-02", "2026-08-03"]


def test_monthly_recurrence_clamps_end_of_month(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Rent", "start_at": "2026-01-31", "all_day": True,
              "recurrence": "monthly"},
    )
    res = client.get(
        f"/api/v1/projects/{pid}/calendar",
        params={"from": "2026-02-01", "to": "2026-02-28"},
    )
    days = [it["start_at"] for it in res.json()["items"]]
    assert days == ["2026-02-28"]  # Jan 31 -> clamped to Feb 28


def test_invalid_recurrence_rejected(client: TestClient) -> None:
    _, pid = _seed(client)
    res = client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Bad", "start_at": "2026-08-01", "recurrence": "hourly"},
    )
    assert res.status_code == 422


def test_ics_export_contains_events(client: TestClient) -> None:
    _, pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/calendar-events",
        json={"title": "Kick, off", "start_at": "2026-08-10T10:00:00+00:00"},
    )
    client.post(
        f"/api/v1/projects/{pid}/milestones",
        json={"title": "Beta", "target_date": "2026-08-15"},
    )
    res = client.get(f"/api/v1/projects/{pid}/calendar.ics")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/calendar")
    body = res.text
    assert "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body
    assert body.count("BEGIN:VEVENT") == 2
    assert "DTSTART:20260810T100000" in body  # timed event, compacted
    assert "DTSTART;VALUE=DATE:20260815" in body  # all-day milestone
    assert "SUMMARY:Kick\\, off" in body  # comma escaped
