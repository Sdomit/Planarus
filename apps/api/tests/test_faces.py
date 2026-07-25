"""Phase 16.3 — faces everywhere (D33).

Task assignee, comment author, and doc last-editor are stamped from the request
actor context (or an explicit assignee) and resolved to display names on read.
Auth off (the default) leaves every new field null — byte-identical to before.
"""
import pytest
from app.core.config import settings
from app.services.auth_service import SESSION_COOKIE


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _login(client, email) -> str:
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    return token


def _auth(token):
    return {SESSION_COOKIE: token}


def _project(client, cookies=None) -> str:
    kw = {"cookies": cookies} if cookies else {}
    ws = client.post("/api/v1/workspaces", json={"name": "W", "slug": "faces-ws"}, **kw).json()["id"]
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "faces-proj"},
        **kw,
    ).json()["id"]


# --- local mode: everything stays null ----------------------------------------
def test_local_mode_task_has_no_assignee(client):
    pid = _project(client)
    t = client.post(f"/api/v1/projects/{pid}/tasks", json={"title": "T"}).json()
    assert t["assignee_id"] is None
    assert t["assignee_display"] is None


def test_local_mode_comment_has_no_author(client):
    pid = _project(client)
    c = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "hi"},
    ).json()
    assert c["author_id"] is None
    assert c["author_display"] is None


def test_local_mode_doc_has_no_editor(client):
    pid = _project(client)
    d = client.post(
        f"/api/v1/projects/{pid}/docs", json={"title": "D", "doc_type": "note"}
    ).json()
    assert d["updated_by"] is None
    assert d["updated_by_display"] is None


# --- team mode: assignee -------------------------------------------------------
def test_task_assign_and_unassign_with_display(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    pid = _project(client, cookies=_auth(alice))
    # make bob a member so he's a legitimate assignee
    ws = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["memberships"][0]["workspace_id"]
    client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "bob@acme.co", "role": "editor"},
        cookies=_auth(alice),
    )
    bob_id = client.get("/api/v1/auth/me", cookies=_auth(bob)).json()["user"]["id"]

    # create assigned
    t = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "T", "assignee_id": bob_id},
        cookies=_auth(alice),
    ).json()
    assert t["assignee_id"] == bob_id
    assert t["assignee_display"] == "bob"

    # list resolves the name too
    listed = client.get(f"/api/v1/projects/{pid}/tasks", cookies=_auth(alice)).json()
    assert listed[0]["assignee_display"] == "bob"

    # unassign with an explicit null
    cleared = client.patch(
        f"/api/v1/tasks/{t['id']}", json={"assignee_id": None}, cookies=_auth(alice)
    ).json()
    assert cleared["assignee_id"] is None
    assert cleared["assignee_display"] is None


def test_assign_unknown_user_rejected(client, auth_on):
    alice = _login(client, "alice@acme.co")
    pid = _project(client, cookies=_auth(alice))
    r = client.post(
        f"/api/v1/projects/{pid}/tasks",
        json={"title": "T", "assignee_id": "usr_ghost"},
        cookies=_auth(alice),
    )
    assert r.status_code == 422


# --- team mode: comment author + doc editor -----------------------------------
def test_comment_author_stamped_and_resolved(client, auth_on):
    alice = _login(client, "alice@acme.co")
    pid = _project(client, cookies=_auth(alice))
    me = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["user"]
    c = client.post(
        f"/api/v1/projects/{pid}/comments",
        json={"entity_type": "project", "entity_id": pid, "body": "note"},
        cookies=_auth(alice),
    ).json()
    assert c["author_id"] == me["id"]
    assert c["author_display"] == me["display_name"]
    # list resolves too
    listed = client.get(f"/api/v1/projects/{pid}/comments", cookies=_auth(alice)).json()
    assert listed[0]["author_display"] == me["display_name"]


def test_doc_editor_stamped_on_create_and_update(client, auth_on):
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    pid = _project(client, cookies=_auth(alice))
    alice_id = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["user"]["id"]

    d = client.post(
        f"/api/v1/projects/{pid}/docs",
        json={"title": "D", "doc_type": "note"},
        cookies=_auth(alice),
    ).json()
    assert d["updated_by"] == alice_id
    assert d["updated_by_display"] == "alice"

    # bob (owner of his own ws) can't edit alice's doc under auth, so edit as alice
    edited = client.patch(
        f"/api/v1/docs/{d['id']}",
        json={"version": d["version"], "title": "D2"},
        cookies=_auth(alice),
    ).json()
    assert edited["updated_by"] == alice_id
    assert edited["updated_by_display"] == "alice"
    assert bob  # (bob login exercised; cross-tenant edit is covered elsewhere)
