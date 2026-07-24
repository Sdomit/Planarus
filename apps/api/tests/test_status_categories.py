"""#88 — a custom board column means something.

The bug, exactly as reported: add a column called "Shipped", drag finished tasks
into it, and the roadmap reports 0% done, the bell nags those tasks as overdue
forever, and agents never see a project's in-flight work under a custom name.

Each test below drives one of those surfaces through the supported UI actions.
"""
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.utils import now_utc_plus_hours
from app.mcp.tools import read
from tests.mcp_util import read_cap, seed


def _project(client: TestClient, suffix: str) -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()["id"]


def _status(client: TestClient, pid: str, label: str, category: str | None = None,
            entity_type: str = "task") -> dict:
    body: dict = {"entity_type": entity_type, "label": label}
    if category is not None:
        body["category"] = category
    res = client.post(f"/api/v1/projects/{pid}/status-options", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _task(client: TestClient, pid: str, title: str, **fields) -> dict:
    res = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _set_status(client: TestClient, task_id: str, key: str) -> None:
    res = client.patch(f"/api/v1/tasks/{task_id}", json={"status": key})
    assert res.status_code == 200, res.text


# --- the API surface ----------------------------------------------------------
def test_category_defaults_to_open_and_builtins_report_theirs(client: TestClient) -> None:
    pid = _project(client, "cat1")
    assert _status(client, pid, "In review")["category"] == "open"
    options = client.get(f"/api/v1/projects/{pid}/status-options").json()
    by_key = {o["key"]: o for o in options}
    assert by_key["done"]["category"] == "done"
    assert by_key["canceled"]["category"] == "canceled"
    assert by_key["in_progress"]["category"] == "open"
    assert by_key["in_review"]["category"] == "open"


def test_category_can_be_set_and_changed(client: TestClient) -> None:
    pid = _project(client, "cat2")
    opt = _status(client, pid, "Shipped", "done")
    assert opt["category"] == "done"
    res = client.patch(f"/api/v1/status-options/{opt['id']}", json={"category": "canceled"})
    assert res.status_code == 200
    assert res.json()["category"] == "canceled"


def test_unknown_category_is_rejected(client: TestClient) -> None:
    pid = _project(client, "cat3")
    res = client.post(
        f"/api/v1/projects/{pid}/status-options",
        json={"entity_type": "task", "label": "Shipped", "category": "finished"},
    )
    assert res.status_code == 422


# --- roadmap % ----------------------------------------------------------------
def test_roadmap_counts_a_custom_done_column(client: TestClient) -> None:
    pid = _project(client, "cat4")
    shipped = _status(client, pid, "Shipped", "done")["key"]
    for i in range(4):
        _set_status(client, _task(client, pid, f"t{i}")["id"], shipped)
    data = client.get(f"/api/v1/projects/{pid}/roadmap").json()
    assert data["totals"]["done"] == 4
    assert data["pct_done"] == 100


def test_roadmap_excludes_a_custom_canceled_column(client: TestClient) -> None:
    pid = _project(client, "cat5")
    dropped = _status(client, pid, "Dropped", "canceled")["key"]
    _set_status(client, _task(client, pid, "keep")["id"], "in_progress")
    _set_status(client, _task(client, pid, "drop")["id"], dropped)
    totals = client.get(f"/api/v1/projects/{pid}/roadmap").json()["totals"]
    assert totals == {"total": 1, "done": 0, "in_progress": 1, "blocked": 0}


def test_roadmap_still_ignores_an_open_custom_column(client: TestClient) -> None:
    """The default category keeps the old behavior — nothing silently completes."""
    pid = _project(client, "cat6")
    review = _status(client, pid, "In review")["key"]
    _set_status(client, _task(client, pid, "t")["id"], review)
    data = client.get(f"/api/v1/projects/{pid}/roadmap").json()
    assert data["totals"] == {"total": 1, "done": 0, "in_progress": 0, "blocked": 0}
    assert data["pct_done"] == 0


# --- the notification bell ----------------------------------------------------
def test_finished_work_in_a_custom_column_stops_nagging(client: TestClient) -> None:
    pid = _project(client, "cat7")
    shipped = _status(client, pid, "Shipped", "done")["key"]
    overdue = now_utc_plus_hours(-48)
    late = _task(client, pid, "late", due_at=overdue)
    done = _task(client, pid, "done late", due_at=overdue)
    _set_status(client, done["id"], shipped)
    items = client.get(f"/api/v1/notifications?project_id={pid}").json()["items"]
    overdue_ids = {i["id"] for i in items if i["kind"] == "task_overdue"}
    assert f"task_overdue:{late['id']}" in overdue_ids
    assert f"task_overdue:{done['id']}" not in overdue_ids


# --- the agent brief ----------------------------------------------------------
def test_active_work_sees_a_custom_open_column(client: TestClient, session: Session) -> None:
    ws, pid = seed(client, "cat8")
    review = _status(client, pid, "In review")["key"]
    shipped = _status(client, pid, "Shipped", "done")["key"]
    in_review = _task(client, pid, "waiting on review")
    _set_status(client, in_review["id"], review)
    finished = _task(client, pid, "already shipped")
    _set_status(client, finished["id"], shipped)
    backlog = _task(client, pid, "someday")  # built-in backlog: still excluded

    res = read.get_active_work(session, read_cap(ws, pid), read.ProjectArgs(project_id=pid))
    assert "waiting on review" in res.text
    assert "already shipped" not in res.text
    assert "someday" not in res.text
    assert backlog["status"] == "backlog"


def test_active_phase_skips_a_custom_done_phase_column(
    client: TestClient, session: Session
) -> None:
    ws, pid = seed(client, "cat9")
    shipped = _status(client, pid, "Shipped", "done", entity_type="phase")["key"]
    first = client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Finished phase"}).json()
    client.patch(f"/api/v1/phases/{first['id']}", json={"status": shipped})
    client.post(f"/api/v1/projects/{pid}/phases", json={"title": "Live phase"})

    res = read.get_active_work(session, read_cap(ws, pid), read.ProjectArgs(project_id=pid))
    assert "Live phase" in res.text
    assert "Finished phase" not in res.text
