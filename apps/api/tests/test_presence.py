"""Phase 11.2 — doc presence / soft-lock (D27).

API surface: auth-off 404, session/role/tenant enforcement via the registry
tenant_guard, heartbeat→lock→release flow. Store unit tests cover staleness and
claim ordering with an injectable clock (no sleeping).
"""
import pytest

from app.core.config import settings
from app.schemas.doc import DocCreate
from app.schemas.project import ProjectCreate
from app.schemas.workspace import WorkspaceCreate
from app.services import auth_service, doc_service, project_service, workspace_service
from app.services.auth_service import SESSION_COOKIE
from app.services.presence_service import EDITING, VIEWING, PresenceStore, presence

COOKIE = SESSION_COOKIE


@pytest.fixture(autouse=True)
def _reset_presence():
    presence.reset()
    yield
    presence.reset()


@pytest.fixture(name="env")
def env_fixture(session, monkeypatch):
    """Auth on + one workspace/project/doc + three members: editors A and B,
    viewer C. Users/sessions come straight from the service layer (dev provider
    rows created directly — no HTTP flags loosened)."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    ws = workspace_service.create_workspace(session, WorkspaceCreate(name="T", slug="team"))
    project = project_service.create_project(
        session, ProjectCreate(workspace_id=ws.id, title="P", slug="proj")
    )
    doc = doc_service.create_doc(
        session, project.id, DocCreate(title="Canvas", doc_type="note", editor_format="excalidraw")
    )
    tokens, users = {}, {}
    for name, role in (("ana", "editor"), ("ben", "editor"), ("cal", "viewer")):
        user, token = auth_service.login_with_identity(
            session, "dev", f"{name}@t.lan", f"{name}@t.lan", name.title()
        )
        auth_service.add_member(session, ws.id, user.id, role)
        tokens[name], users[name] = token, user
    return {"doc_id": doc.id, "tokens": tokens, "users": users}


def _beat(client, doc_id, token, mode="editing"):
    return client.put(
        f"/api/v1/docs/{doc_id}/presence", json={"mode": mode}, cookies={COOKIE: token}
    )


# --- gates ----------------------------------------------------------------------
def test_presence_404_when_auth_off(client, session):
    ws = workspace_service.create_workspace(session, WorkspaceCreate(name="S", slug="solo"))
    project = project_service.create_project(
        session, ProjectCreate(workspace_id=ws.id, title="P", slug="solo-p")
    )
    doc = doc_service.create_doc(session, project.id, DocCreate(title="D", doc_type="note"))
    assert client.put(f"/api/v1/docs/{doc.id}/presence", json={"mode": "viewing"}).status_code == 404
    assert client.get(f"/api/v1/docs/{doc.id}/presence").status_code == 404
    assert client.delete(f"/api/v1/docs/{doc.id}/presence").status_code == 404


def test_presence_requires_session(client, env):
    assert client.get(f"/api/v1/docs/{env['doc_id']}/presence").status_code == 401


def test_presence_unknown_doc_404(client, env):
    assert _beat(client, "doc_missing", env["tokens"]["ana"]).status_code == 404


def test_viewer_watches_but_never_beats(client, env):
    doc_id, t = env["doc_id"], env["tokens"]
    assert _beat(client, doc_id, t["cal"]).status_code == 403  # tenant_guard WRITE roles
    assert client.delete(f"/api/v1/docs/{doc_id}/presence", cookies={COOKIE: t["cal"]}).status_code == 403
    r = client.get(f"/api/v1/docs/{doc_id}/presence", cookies={COOKIE: t["cal"]})
    assert r.status_code == 200
    assert r.json()["you"] == env["users"]["cal"].id


def test_non_member_403(client, session, env):
    user, token = auth_service.login_with_identity(
        session, "dev", "out@side.er", "out@side.er", "Outsider"
    )
    assert _beat(client, env["doc_id"], token).status_code == 403
    assert (
        client.get(f"/api/v1/docs/{env['doc_id']}/presence", cookies={COOKIE: token}).status_code
        == 403
    )


# --- lock flow ------------------------------------------------------------------
def test_first_editor_wins_and_release(client, env):
    doc_id, t, u = env["doc_id"], env["tokens"], env["users"]
    r = _beat(client, doc_id, t["ana"])
    assert r.status_code == 200
    body = r.json()
    assert body["editor_user_id"] == u["ana"].id
    assert body["you"] == u["ana"].id

    r = _beat(client, doc_id, t["ben"])  # second claim: ana keeps the lock
    body = r.json()
    assert body["editor_user_id"] == u["ana"].id
    assert body["you"] == u["ben"].id
    assert {e["user_id"] for e in body["entries"]} == {u["ana"].id, u["ben"].id}

    # viewer sees who's editing
    r = client.get(f"/api/v1/docs/{doc_id}/presence", cookies={COOKIE: t["cal"]})
    assert r.json()["editor_user_id"] == u["ana"].id

    # explicit leave hands the lock to the waiting claimant
    assert (
        client.delete(f"/api/v1/docs/{doc_id}/presence", cookies={COOKIE: t["ana"]}).status_code
        == 204
    )
    assert _beat(client, doc_id, t["ben"]).json()["editor_user_id"] == u["ben"].id


def test_dropping_to_viewing_releases_lock(client, env):
    doc_id, t, u = env["doc_id"], env["tokens"], env["users"]
    assert _beat(client, doc_id, t["ana"]).json()["editor_user_id"] == u["ana"].id
    assert _beat(client, doc_id, t["ana"], mode="viewing").json()["editor_user_id"] is None
    assert _beat(client, doc_id, t["ben"]).json()["editor_user_id"] == u["ben"].id


def _project_of(session, doc_id):
    from app.models.doc import Doc

    return session.get(Doc, doc_id).project_id


def test_docs_isolated_and_no_email_leak(client, session, env):
    doc_id, t = env["doc_id"], env["tokens"]
    other = doc_service.create_doc(
        session, _project_of(session, doc_id), DocCreate(title="Other", doc_type="note")
    )
    _beat(client, doc_id, t["ana"])
    r = _beat(client, other.id, t["ben"])
    body = r.json()
    assert {e["user_id"] for e in body["entries"]} == {env["users"]["ben"].id}
    assert "@" not in r.text  # display names + ids only, never emails


def test_invalid_mode_422(client, env):
    r = client.put(
        f"/api/v1/docs/{env['doc_id']}/presence",
        json={"mode": "owning"},
        cookies={COOKIE: env["tokens"]["ana"]},
    )
    assert r.status_code == 422


# --- store unit tests (injectable clock — no sleeping) ---------------------------
def test_store_staleness_expires_lock():
    t = [0.0]
    store = PresenceStore(ttl_seconds=30.0, clock=lambda: t[0])
    store.heartbeat("d", "u1", "Ana", EDITING)
    t[0] = 10.0
    store.heartbeat("d", "u2", "Ben", EDITING)
    assert store.snapshot("d")["editor_user_id"] == "u1"
    t[0] = 35.0  # u1 stale (last beat 0), u2 fresh via a new beat
    view = store.heartbeat("d", "u2", "Ben", EDITING)
    assert view["editor_user_id"] == "u2"
    assert [e["user_id"] for e in view["entries"]] == ["u2"]
    t[0] = 70.0  # everyone stale
    assert store.snapshot("d") == {"entries": [], "editor_user_id": None, "ttl_seconds": 30}


def test_store_reclaim_goes_to_back_of_queue():
    t = [0.0]
    store = PresenceStore(clock=lambda: t[0])
    store.heartbeat("d", "u1", "Ana", EDITING)
    t[0] = 1.0
    store.heartbeat("d", "u2", "Ben", EDITING)
    t[0] = 2.0
    store.heartbeat("d", "u1", "Ana", VIEWING)  # release
    t[0] = 3.0
    view = store.heartbeat("d", "u1", "Ana", EDITING)  # re-claim: now behind u2
    assert view["editor_user_id"] == "u2"


def test_store_user_cap_drops_stalest():
    t = [0.0]
    store = PresenceStore(max_users=2, clock=lambda: t[0])
    store.heartbeat("d", "u1", "A", VIEWING)
    t[0] = 1.0
    store.heartbeat("d", "u2", "B", VIEWING)
    t[0] = 2.0
    view = store.heartbeat("d", "u3", "C", VIEWING)
    assert {e["user_id"] for e in view["entries"]} == {"u2", "u3"}
