"""Phase 9 in-app notification feed (computed, no table)."""
from app.core.utils import now_utc, now_utc_plus_hours
from app.models.project import Project
from app.services import approval_service
from fastapi.testclient import TestClient
from sqlmodel import Session


def _seed(client: TestClient, suffix: str = "ntf") -> str:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": f"Proj {suffix}", "slug": f"p-{suffix}"},
    ).json()
    return proj["id"]


_PAST = "2000-01-01T00:00:00+00:00"


def test_feed_empty(client: TestClient) -> None:
    pid = _seed(client)
    res = client.get(f"/api/v1/notifications?project_id={pid}")
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == []
    assert data["generated_at"]


def test_feed_project_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/notifications?project_id=proj_nope").status_code == 404


def test_feed_task_buckets(client: TestClient) -> None:
    pid = _seed(client)
    client.post(
        f"/api/v1/projects/{pid}/tasks", json={"title": "Late", "due_at": _PAST}
    )
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Soon", "due_at": now_utc_plus_hours(2)},
    )
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Far", "due_at": now_utc_plus_hours(24 * 30)},
    )
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Done late", "due_at": _PAST, "status": "done"},
    )
    items = client.get(f"/api/v1/notifications?project_id={pid}").json()["items"]
    kinds = {i["id"].split(":")[0] for i in items}
    titles = [i["title"] for i in items]
    assert "task_overdue" in kinds
    assert "task_due_soon" in kinds
    assert any("Late" in t for t in titles)
    assert any("Soon" in t for t in titles)
    assert not any("Far" in t for t in titles)  # beyond the 48h window
    assert not any("Done late" in t for t in titles)  # done tasks never remind


def test_feed_blocker_and_severity_order(client: TestClient, session: Session) -> None:
    pid = _seed(client, suffix="ntf2")
    client.post(f"/api/v1/projects/{pid}/blockers", json={"title": "Stuck on infra"})
    client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "Due", "due_at": now_utc_plus_hours(2)},
    )
    approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "From MCP"}
    )
    items = client.get(f"/api/v1/notifications?project_id={pid}").json()["items"]
    severities = [i["severity"] for i in items]
    # actions first, then warnings, then info
    assert severities == sorted(severities, key={"action": 0, "warn": 1, "info": 2}.get)
    kinds = [i["kind"] for i in items]
    # A fresh proposal has ~24h left — pending, not yet "expiring soon" (<6h).
    assert kinds[0] == "approval_pending"
    assert "blocker_open" in kinds
    assert "task_due_soon" in kinds


def test_feed_flags_expiring_and_hides_stale_proposals(
    client: TestClient, session: Session
) -> None:
    pid = _seed(client, suffix="ntf3")
    expiring = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "Soonish"}
    )
    expiring.expires_at = now_utc_plus_hours(1)  # inside the 6h warning window
    stale = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "Too old"}
    )
    stale.expires_at = _PAST  # already expired — cannot be applied, so hidden
    session.add(expiring)
    session.add(stale)
    session.commit()

    items = client.get(f"/api/v1/notifications?project_id={pid}").json()["items"]
    kinds = {i["id"]: i["kind"] for i in items}
    assert kinds.get(f"approval_expiring:{expiring.id}") == "approval_expiring"
    assert not any(stale.id in item_id for item_id in kinds)


def test_feed_workspace_wide_and_archived_excluded(
    client: TestClient, session: Session
) -> None:
    pid_a = _seed(client, suffix="ntfa")
    pid_b = _seed(client, suffix="ntfb")
    client.post(f"/api/v1/projects/{pid_a}/blockers", json={"title": "A blocked"})
    client.post(f"/api/v1/projects/{pid_b}/blockers", json={"title": "B blocked"})

    items = client.get("/api/v1/notifications").json()["items"]
    projects = {i["project_id"] for i in items}
    assert {pid_a, pid_b} <= projects
    assert all(i["project_title"] for i in items)

    # Archive B → its items disappear from the workspace-wide feed.
    project_b = session.get(Project, pid_b)
    assert project_b is not None
    project_b.archived_at = now_utc()
    session.add(project_b)
    session.commit()
    items = client.get("/api/v1/notifications").json()["items"]
    assert pid_b not in {i["project_id"] for i in items}
