"""Phase 10.2b — cross-tenant denial sweep over every project-scoped domain route.

With auth enabled, an authenticated NON-MEMBER of the owning workspace must be
denied (403/404) on every domain route — nested collections, flat item routes,
and the query-param list routes — proving the registry-driven `tenant_guard`
covers the whole surface, not just the P10.2 crown-jewel routes. Also asserts the
guard is a complete no-op when auth is off.
"""
import pytest
from app.core.config import settings
from app.services.auth_service import SESSION_COOKIE

COOKIE = SESSION_COOKIE


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _login(client, email) -> str:
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    token = client.cookies.get(COOKIE)
    client.cookies.clear()
    return token


def _auth(token):
    return {COOKIE: token}


def _owned_project(client, session, token, slug):
    """Owner creates a workspace (auto-owned) + a project + a phase and a task,
    returning real ids to probe as an outsider (the nested collection probes cover
    the remaining entity kinds at the collection level)."""
    from app.schemas.phase import PhaseCreate
    from app.schemas.task import TaskCreate
    from app.services import phase_service, task_service

    ws = client.post(
        "/api/v1/workspaces", json={"name": slug, "slug": slug}, cookies=_auth(token)
    ).json()["id"]
    pid = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": f"{slug}p"},
        cookies=_auth(token),
    ).json()["id"]
    phase = phase_service.create_phase(session, pid, PhaseCreate(title="Ph"))
    task = task_service.create_task(session, pid, TaskCreate(title="T"))
    return {
        "workspace_id": ws,
        "project_id": pid,
        "phase_id": phase.id,
        "task_id": task.id,
    }


def test_cross_tenant_denied_across_domain_routes(client, session, auth_on):
    owner = _login(client, "owner@acme.co")
    ids = _owned_project(client, session, owner, "acme")
    outsider = _login(client, "outsider@evil.co")
    pid = ids["project_id"]

    # (method, path) covering nested collections, flat item routes, and the
    # query-param list/feed routes. An outsider must never get 2xx.
    probes = [
        ("GET", f"/api/v1/projects/{pid}/phases"),
        ("GET", f"/api/v1/projects/{pid}/tasks"),
        ("GET", f"/api/v1/projects/{pid}/stages"),
        ("GET", f"/api/v1/projects/{pid}/decisions"),
        ("GET", f"/api/v1/projects/{pid}/risks"),
        ("GET", f"/api/v1/projects/{pid}/blockers"),
        ("GET", f"/api/v1/projects/{pid}/milestones"),
        ("GET", f"/api/v1/projects/{pid}/comments"),
        ("GET", f"/api/v1/projects/{pid}/links"),
        ("GET", f"/api/v1/projects/{pid}/docs"),
        ("GET", f"/api/v1/projects/{pid}/roadmap"),
        ("GET", f"/api/v1/projects/{pid}/timeline"),
        ("GET", f"/api/v1/projects/{pid}/git"),
        ("GET", f"/api/v1/projects/{pid}/agent-runs"),
        ("GET", f"/api/v1/projects/{pid}/notification-rules"),
        ("GET", f"/api/v1/projects/{pid}/email-log"),
        ("GET", f"/api/v1/projects/{pid}/context-pack/sources"),
        ("POST", f"/api/v1/projects/{pid}/context/regenerate"),
        ("POST", f"/api/v1/projects/{pid}/tasks"),
        ("PATCH", f"/api/v1/tasks/{ids['task_id']}"),
        ("PATCH", f"/api/v1/phases/{ids['phase_id']}"),
        ("GET", f"/api/v1/context-files?project_id={pid}"),
        ("GET", f"/api/v1/notifications?project_id={pid}"),
        ("GET", f"/api/v1/approvals?project_id={pid}"),
    ]
    for method, path in probes:
        r = client.request(method, path, json={}, cookies=_auth(outsider))
        assert r.status_code in (403, 404), f"{method} {path} -> {r.status_code} (leak!)"

    # ...and the owner is allowed through a representative subset.
    assert client.get(f"/api/v1/projects/{pid}/tasks", cookies=_auth(owner)).status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/roadmap", cookies=_auth(owner)).status_code == 200


def test_sweep_routes_open_when_auth_off(client, session):
    # The same routes must work with no auth (guard is a complete no-op) — no login below.
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "woff"}).json()["id"]
    pid = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "poff"}
    ).json()["id"]
    assert client.get(f"/api/v1/projects/{pid}/tasks").status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/roadmap").status_code == 200
    assert client.get(f"/api/v1/context-files?project_id={pid}").status_code == 200
