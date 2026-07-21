"""Phase 10.2 — tenant enforcement (hosted mode).

Verifies that, WITH auth enabled, the workspace/project boundaries and the D22
approver gate reject cross-tenant / under-privileged callers — and that WITHOUT
auth (the default) none of it changes behavior. Membership RBAC internals are
covered in test_auth_identity.py; here we focus on the domain-route enforcement.
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


def _mk_owned_workspace(client, token, slug) -> str:
    """Create a workspace as the logged-in caller (auto-owned in hosted mode)."""
    r = client.post(
        "/api/v1/workspaces", json={"name": slug, "slug": slug}, cookies=_auth(token)
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- disabled by default → unchanged ------------------------------------------
def test_domain_routes_unchanged_when_auth_off(client):
    r = client.post("/api/v1/workspaces", json={"name": "W", "slug": "woff"})
    ws = r.json()["id"]
    # no cookie, no auth → still fully usable (local single-user mode)
    p = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "proj"}
    )
    assert p.status_code == 201
    assert client.get("/api/v1/projects").status_code == 200
    assert client.get(f"/api/v1/projects/{p.json()['id']}").status_code == 200


def test_domain_route_requires_login_when_auth_on(client, auth_on):
    # With auth enabled, a domain route with no session → 401 (not 404).
    assert client.get("/api/v1/projects").status_code == 401
    assert client.get("/api/v1/workspaces").status_code == 401


# --- workspace + project scoping ----------------------------------------------
def test_workspace_and_project_lists_scoped_to_membership(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws_a = _mk_owned_workspace(client, alice, "alice-ws")
    ws_b = _mk_owned_workspace(client, bob, "bob-ws")

    # Alice sees only her workspace/project; Bob's are invisible.
    a_ws = client.get("/api/v1/workspaces", cookies=_auth(alice)).json()
    assert [w["id"] for w in a_ws] == [ws_a]

    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_a, "title": "A", "slug": "aproj"},
        cookies=_auth(alice),
    )
    client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_b, "title": "B", "slug": "bproj"},
        cookies=_auth(bob),
    )
    a_projects = client.get("/api/v1/projects", cookies=_auth(alice)).json()
    assert {p["workspace_id"] for p in a_projects} == {ws_a}


def test_cross_tenant_project_read_forbidden(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws_b = _mk_owned_workspace(client, bob, "bob-ws")
    pid = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_b, "title": "B", "slug": "bproj"},
        cookies=_auth(bob),
    ).json()["id"]

    # Alice (not a member of Bob's workspace) cannot read his project.
    assert client.get(f"/api/v1/projects/{pid}", cookies=_auth(alice)).status_code == 403
    # ...but Bob can.
    assert client.get(f"/api/v1/projects/{pid}", cookies=_auth(bob)).status_code == 200


def test_create_project_requires_workspace_write_role(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws_a = _mk_owned_workspace(client, alice, "alice-ws")

    # Bob is not a member → cannot create a project in Alice's workspace.
    r = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_a, "title": "X", "slug": "xproj"},
        cookies=_auth(bob),
    )
    assert r.status_code == 403

    # Add Bob as viewer → still cannot write (needs editor/owner).
    ug = client.get("/api/v1/auth/me", cookies=_auth(bob)).json()["user"]["id"]
    client.post(
        f"/api/v1/workspaces/{ws_a}/members",
        json={"email": "bob@acme.co", "role": "viewer"},
        cookies=_auth(alice),
    )
    r2 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_a, "title": "X", "slug": "xproj"},
        cookies=_auth(bob),
    )
    assert r2.status_code == 403

    # Promote to editor → now allowed.
    client.patch(
        f"/api/v1/workspaces/{ws_a}/members/{ug}",
        json={"role": "editor"},
        cookies=_auth(alice),
    )
    r3 = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_a, "title": "X", "slug": "xproj"},
        cookies=_auth(bob),
    )
    assert r3.status_code == 201


def test_viewer_cannot_update_project(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws_a = _mk_owned_workspace(client, alice, "alice-ws")
    pid = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws_a, "title": "A", "slug": "aproj"},
        cookies=_auth(alice),
    ).json()["id"]
    client.post(
        f"/api/v1/workspaces/{ws_a}/members",
        json={"email": "bob@acme.co", "role": "viewer"},
        cookies=_auth(alice),
    )
    # viewer can read...
    assert client.get(f"/api/v1/projects/{pid}", cookies=_auth(bob)).status_code == 200
    # ...but not update
    r = client.patch(
        f"/api/v1/projects/{pid}", json={"title": "hacked"}, cookies=_auth(bob)
    )
    assert r.status_code == 403


def test_workspace_creator_auto_owns(client, auth_on):
    alice = _login(client, "alice@acme.co")
    ws = _mk_owned_workspace(client, alice, "alice-ws")
    me = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()
    assert {"workspace_id": ws, "role": "owner"} in me["memberships"]


# --- D22: approver-role gating on the apply path ------------------------------
def test_approver_gate_requires_owner(client, session, auth_on):
    from app.services import approval_service

    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws = _mk_owned_workspace(client, alice, "alice-ws")
    pid = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "pproj"},
        cookies=_auth(alice),
    ).json()["id"]
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "T"}
    )
    hdr = {"X-Planarus-Local-Token": client.get("/api/v1/local-session").json()["token"]}

    # Non-member with a valid control token still cannot approve (D22).
    r = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=hdr, cookies=_auth(bob))
    assert r.status_code == 403

    # Editor is not an approver — owner-only.
    ug = client.get("/api/v1/auth/me", cookies=_auth(bob)).json()["user"]["id"]
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "bob@acme.co", "role": "editor"},
        cookies=_auth(alice),
    )
    r2 = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=hdr, cookies=_auth(bob))
    assert r2.status_code == 403

    # The workspace owner can.
    r3 = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=hdr, cookies=_auth(alice))
    assert r3.status_code == 200, r3.text


def test_approver_gate_noop_when_auth_off(client, session):
    # With auth off, approve works with just the control token (unchanged 7A flow).
    from app.services import approval_service

    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "wapr"}).json()["id"]
    pid = client.post(
        "/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "papr"}
    ).json()["id"]
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "T"}
    )
    hdr = {"X-Planarus-Local-Token": client.get("/api/v1/local-session").json()["token"]}
    assert client.post(f"/api/v1/approvals/{ar.id}/approve", headers=hdr).status_code == 200
