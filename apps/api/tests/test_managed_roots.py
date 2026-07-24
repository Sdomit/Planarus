"""#115 slice 115.1 — enforcement of managed project roots at the API boundary.

Auth mode: the on-disk root is server-owned and derived from ids; a tenant-
supplied folder_path has no effect. Local mode: the escape hatch works but
obviously-dangerous and overlapping roots are rejected. Plus the fail-closed
startup precondition.
"""
import os

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


# --- auth mode: root is server-derived, tenant path ignored, path not leaked --
def test_auth_mode_derives_root_and_ignores_tenant_path(client, auth_on, session):
    from app.models.project import Project

    token = _login(client, "alice@acme.co")
    ws = client.post(
        "/api/v1/workspaces", json={"name": "acme", "slug": "acme"}, cookies=_auth(token)
    ).json()["id"]

    # A tenant tries to point the project at an arbitrary absolute path.
    r = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "proj", "folder_path": "/etc"},
        cookies=_auth(token),
    )
    assert r.status_code == 201, r.text
    proj = r.json()
    # The absolute server root is redacted from the response (issue point 6).
    assert proj["folder_path"] is None
    # But on disk it is the derived, non-tenant-chosen path under the base.
    base = os.path.realpath(settings.projects_root)
    stored = session.get(Project, proj["id"]).folder_path
    assert stored == os.path.join(base, ws, proj["id"])


# --- local mode: escape hatch works, but guards apply -------------------------
def test_local_mode_accepts_a_normal_absolute_folder(client, tmp_path):
    ws = client.post("/api/v1/workspaces", json={"name": "w", "slug": "wloc"}).json()["id"]
    folder = str(tmp_path / "myproj")
    r = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "pp", "folder_path": folder},
    )
    assert r.status_code == 201, r.text
    assert r.json()["folder_path"] == os.path.realpath(folder)


def test_local_mode_rejects_dangerous_root(client):
    ws = client.post("/api/v1/workspaces", json={"name": "w", "slug": "wdang"}).json()["id"]
    r = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": ws,
            "title": "P",
            "slug": "pp",
            "folder_path": os.path.abspath(os.sep),  # filesystem/drive root
        },
    )
    assert r.status_code == 422, r.text


def test_local_mode_rejects_overlapping_root(client, tmp_path):
    ws = client.post("/api/v1/workspaces", json={"name": "w", "slug": "wov"}).json()["id"]
    parent = str(tmp_path / "shared")
    os.makedirs(parent)
    first = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "A", "slug": "aa", "folder_path": parent},
    )
    assert first.status_code == 201, first.text
    # A second project nested inside the first's root must be refused.
    second = client.post(
        "/api/v1/projects",
        json={
            "workspace_id": ws,
            "title": "B",
            "slug": "bb",
            "folder_path": os.path.join(parent, "child"),
        },
    )
    assert second.status_code == 409, second.text


def test_local_mode_update_cannot_repoint_onto_another_project(client, tmp_path):
    ws = client.post("/api/v1/workspaces", json={"name": "w", "slug": "wup"}).json()["id"]
    a = str(tmp_path / "a")
    b = str(tmp_path / "b")
    os.makedirs(a)
    os.makedirs(b)
    pa = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "A", "slug": "aa", "folder_path": a},
    ).json()
    pb = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "B", "slug": "bb", "folder_path": b},
    ).json()
    # Repointing B onto A's root is an overlap → 409.
    r = client.patch(f"/api/v1/projects/{pb['id']}", json={"folder_path": a})
    assert r.status_code == 409, r.text
    # A's root is untouched.
    assert client.get(f"/api/v1/projects/{pa['id']}").json()["folder_path"] == os.path.realpath(a)


# --- startup fail-closed ------------------------------------------------------
def test_startup_fails_closed_without_projects_root(monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "projects_root", "")
    with pytest.raises(RuntimeError, match="PLANARUS_PROJECTS_ROOT"):
        create_app()
