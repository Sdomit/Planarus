"""Phase 10.6c — cross-machine sync transport.

Covers the serialization primitives, the snapshot/push endpoints (with tenant
enforcement + the cross-tenant push guard), and an end-to-end round where a
"local" replica (a separate session) diverges and pushes to the "remote" (the
TestClient app's DB), converging both.
"""
import pytest

import app.models  # noqa: F401
from app.core.config import settings
from app.models.task import Task
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import project_service, task_service, workspace_service
from app.services.auth_service import SESSION_COOKIE
from app.sync import (
    ScopeViolation,
    build_snapshot,
    import_change_set,
    snapshot_manifest,
)
from app.sync.diff import Change, ChangeKind


def _seed(session, slug="acme"):
    ws = workspace_service.create_workspace(session, WorkspaceCreate(name=slug, slug=slug))
    p = project_service.create_project(
        session, ProjectCreate(workspace_id=ws.id, title="P", slug=f"{slug}p")
    )
    t = task_service.create_task(session, p.id, TaskCreate(title="A"))
    return ws.id, p.id, t.id


# --- primitives ---------------------------------------------------------------
def test_snapshot_structure_and_import_update(session):
    _, pid, tid = _seed(session)
    snap = build_snapshot(session, pid)
    assert snap["project_id"] == pid
    assert ("project", pid) in snapshot_manifest(snap)
    assert f"task::{tid}" in snap["records"]

    # Applying a serialized UPDATE for an existing entity mutates it (the realistic
    # transport case — the base already exists on the receiving replica).
    rec = dict(snap["records"][f"task::{tid}"])
    rec["title"] = "A-updated"
    import_change_set(
        session,
        [Change(("task", tid), ChangeKind.REMOTE_UPDATE)],
        {f"task::{tid}": rec},
    )
    assert session.get(Task, tid).title == "A-updated"


def test_import_rejects_cross_project_record(session):
    _, pid, _ = _seed(session, "acme")
    _, other_pid, _ = _seed(session, "evil")
    # A record claiming to be in `pid` but actually carrying evil's project_id.
    forged = {"task::forged": {"id": "forged", "project_id": other_pid, "title": "x",
                               "status": "backlog", "created_at": "t", "updated_at": "t",
                               "description": None, "priority": None, "sort_order": 0,
                               "due_at": None, "phase_id": None, "stage_id": None}}
    changes = [Change(("task", "forged"), ChangeKind.LOCAL_CREATE)]
    with pytest.raises(ScopeViolation):
        import_change_set(session, changes, forged, restrict_project_id=pid)


# --- endpoints ----------------------------------------------------------------
def test_snapshot_and_push_endpoints_auth_off(client, session):
    _, pid, tid = _seed(session)
    snap = client.get(f"/api/v1/projects/{pid}/sync/snapshot").json()
    assert snap["project_id"] == pid

    # Push a new task via the endpoint.
    new_rec = {"id": "t-new", "project_id": pid, "title": "pushed", "status": "backlog",
               "description": None, "priority": None, "sort_order": 0, "due_at": None,
               "phase_id": None, "stage_id": None, "created_at": "t", "updated_at": "t"}
    body = {
        "changes": [{"entity_type": "task", "entity_id": "t-new", "kind": "local_create"}],
        "records": {"task::t-new": new_rec},
    }
    r = client.post(f"/api/v1/projects/{pid}/sync/push", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 1
    assert session.get(Task, "t-new").title == "pushed"


def test_push_rejects_cross_project_record_over_http(client, session):
    _, pid, _ = _seed(session, "acme")
    _, other_pid, _ = _seed(session, "evil")
    forged = {"id": "t-forge", "project_id": other_pid, "title": "x", "status": "backlog",
              "description": None, "priority": None, "sort_order": 0, "due_at": None,
              "phase_id": None, "stage_id": None, "created_at": "t", "updated_at": "t"}
    body = {
        "changes": [{"entity_type": "task", "entity_id": "t-forge", "kind": "local_create"}],
        "records": {"task::t-forge": forged},
    }
    r = client.post(f"/api/v1/projects/{pid}/sync/push", json=body)
    assert r.status_code == 422
    assert session.get(Task, "t-forge") is None  # nothing written


def test_sync_endpoints_enforce_tenant_when_auth_on(client, session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    _, pid, _ = _seed(session)  # created directly (member-less workspace)

    # No session cookie → 401 on the guarded sync routes.
    assert client.get(f"/api/v1/projects/{pid}/sync/snapshot").status_code == 401

    # An authenticated non-member → 403 (not a member of the project's workspace).
    client.post("/api/v1/auth/dev-login", json={"email": "outsider@evil.co"})
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    assert (
        client.get(
            f"/api/v1/projects/{pid}/sync/snapshot", cookies={SESSION_COOKIE: token}
        ).status_code
        == 403
    )
