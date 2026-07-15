"""Phase 10.1 — identity + workspace membership (hosted mode).

Covers the disabled-by-default surface, dev-login/session/logout, and the
membership RBAC (bootstrap, owner-only management, last-owner protection). Auth is
off by default, so every test that needs it flips the settings flags via
monkeypatch (auto-reverted), mirroring the `external_api` fixture pattern.
"""
import pytest

from app.core.config import settings
from app.services.auth_service import SESSION_COOKIE

COOKIE = SESSION_COOKIE


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    """Enable hosted auth + the dev-login provider for the test."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _mk_workspace(client, slug="acme") -> str:
    r = client.post("/api/v1/workspaces", json={"name": slug.title(), "slug": slug})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _login(client, email, display_name=None) -> str:
    """Dev-login and return the raw session token; leaves the jar clean so callers
    pass the cookie explicitly (keeps multi-user tests unambiguous)."""
    body = {"email": email}
    if display_name:
        body["display_name"] = display_name
    r = client.post("/api/v1/auth/dev-login", json=body)
    assert r.status_code == 200, r.text
    token = client.cookies.get(COOKIE)
    assert token
    client.cookies.clear()
    return token


def _auth(token):
    return {COOKIE: token}


# --- disabled by default ------------------------------------------------------
def test_auth_surface_404_when_disabled(client):
    ws = _mk_workspace(client)
    assert client.get("/api/v1/auth/me").status_code == 404
    assert client.post("/api/v1/auth/dev-login", json={"email": "a@b.co"}).status_code == 404
    assert client.get(f"/api/v1/workspaces/{ws}/members").status_code == 404


def test_existing_routes_unchanged_when_disabled(client):
    # The core local-mode surface must behave exactly as before (no auth needed).
    ws = _mk_workspace(client, "solo")
    assert client.get("/api/v1/workspaces").status_code == 200
    r = client.post("/api/v1/projects", json={"workspace_id": ws, "title": "P", "slug": "proj"})
    assert r.status_code == 201, r.text


def test_dev_login_404_when_auth_on_but_dev_off(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", False)
    r = client.post("/api/v1/auth/dev-login", json={"email": "a@b.co"})
    assert r.status_code == 404


# --- login / session / logout -------------------------------------------------
def test_dev_login_me_logout_flow(client, auth_on):
    r = client.post(
        "/api/v1/auth/dev-login", json={"email": "Owner@Acme.CO", "display_name": "Owny"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "owner@acme.co"  # normalized
    assert body["user"]["display_name"] == "Owny"
    assert body["memberships"] == []
    token = client.cookies.get(COOKIE)
    client.cookies.clear()

    me = client.get("/api/v1/auth/me", cookies=_auth(token))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "owner@acme.co"

    assert client.post("/api/v1/auth/logout", cookies=_auth(token)).status_code == 204
    assert client.get("/api/v1/auth/me", cookies=_auth(token)).status_code == 401


def test_me_requires_valid_session(client, auth_on):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", cookies=_auth("bogus")).status_code == 401


def test_dev_login_is_idempotent_on_user(client, auth_on):
    t1 = _login(client, "same@acme.co")
    t2 = _login(client, "same@acme.co")
    u1 = client.get("/api/v1/auth/me", cookies=_auth(t1)).json()["user"]["id"]
    u2 = client.get("/api/v1/auth/me", cookies=_auth(t2)).json()["user"]["id"]
    assert u1 == u2  # same user, distinct sessions


def test_expired_session_rejected(client, auth_on, monkeypatch):
    monkeypatch.setattr(settings, "auth_session_ttl_hours", -1)  # already expired
    token = _login(client, "exp@acme.co")
    assert client.get("/api/v1/auth/me", cookies=_auth(token)).status_code == 401


# --- membership bootstrap + RBAC ----------------------------------------------
def test_bootstrap_requires_self_as_owner(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")

    # non-owner role on empty workspace → 403
    bad = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "viewer"},
        cookies=_auth(owner),
    )
    assert bad.status_code == 403

    # adding someone else before claiming → 403
    _login(client, "other@acme.co")
    bad2 = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "other@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    assert bad2.status_code == 403

    ok = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["role"] == "owner"


def test_owner_manages_members_and_editor_cannot(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")
    editor = _login(client, "editor@acme.co")
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    # owner adds the editor
    r = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "editor@acme.co", "role": "editor"},
        cookies=_auth(owner),
    )
    assert r.status_code == 201, r.text

    # editor can see the roster...
    assert client.get(f"/api/v1/workspaces/{ws}/members", cookies=_auth(editor)).status_code == 200
    # ...but cannot add members (owner-only)
    third = _login(client, "third@acme.co")
    denied = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "third@acme.co", "role": "viewer"},
        cookies=_auth(editor),
    )
    assert denied.status_code == 403
    # a complete outsider cannot even list
    assert client.get(f"/api/v1/workspaces/{ws}/members", cookies=_auth(third)).status_code == 403


def test_add_unknown_email_404(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    r = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "ghost@acme.co", "role": "viewer"},
        cookies=_auth(owner),
    )
    assert r.status_code == 404


def test_duplicate_member_conflict(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")
    _login(client, "dup@acme.co")
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    a = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "dup@acme.co", "role": "editor"},
        cookies=_auth(owner),
    )
    assert a.status_code == 201
    b = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "dup@acme.co", "role": "viewer"},
        cookies=_auth(owner),
    )
    assert b.status_code == 409


def test_last_owner_protection(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")
    ug = client.get("/api/v1/auth/me", cookies=_auth(owner)).json()["user"]["id"]
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    # cannot demote or remove the only owner
    assert client.patch(
        f"/api/v1/workspaces/{ws}/members/{ug}",
        json={"role": "editor"},
        cookies=_auth(owner),
    ).status_code == 409
    assert client.delete(
        f"/api/v1/workspaces/{ws}/members/{ug}", cookies=_auth(owner)
    ).status_code == 409

    # promote a second owner, then the first can be demoted
    second = _login(client, "second@acme.co")
    sg = client.get("/api/v1/auth/me", cookies=_auth(second)).json()["user"]["id"]
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "second@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    assert client.patch(
        f"/api/v1/workspaces/{ws}/members/{ug}",
        json={"role": "editor"},
        cookies=_auth(owner),
    ).status_code == 200


def test_membership_appears_in_me(client, auth_on):
    ws = _mk_workspace(client)
    owner = _login(client, "owner@acme.co")
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "owner@acme.co", "role": "owner"},
        cookies=_auth(owner),
    )
    me = client.get("/api/v1/auth/me", cookies=_auth(owner)).json()
    assert me["memberships"] == [{"workspace_id": ws, "role": "owner"}]


def test_members_route_404_when_disabled_even_with_cookie(client, monkeypatch):
    # Belt-and-suspenders: with auth off the members surface must not exist.
    ws = _mk_workspace(client)
    assert client.patch(
        f"/api/v1/workspaces/{ws}/members/x", json={"role": "editor"}
    ).status_code == 404
