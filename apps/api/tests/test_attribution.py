"""Phase 16.0 — attribution spine (D32).

With auth ON, audited writes stamp the acting user into ``AuditEvent.actor_id``
(via the request-scoped actor context), approvals record the real approver in
``decided_by``, and the timeline / approval read models expose resolved display
names. With auth OFF (the default), everything stays byte-identical to the
pre-Phase-16 behavior: actor_id None, decided_by ``"local"``, displays None.
"""
import pytest

from app.core.config import settings
from app.services import approval_service
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


def _control(client) -> dict:
    return {
        "X-Approvo-Local-Token": client.get("/api/v1/local-session").json()["token"]
    }


def _mk_project(client, cookies=None) -> str:
    kw = {"cookies": cookies} if cookies else {}
    ws = client.post(
        "/api/v1/workspaces", json={"name": "W", "slug": "attr-ws"}, **kw
    ).json()["id"]
    return client.post(
        "/api/v1/projects",
        json={"workspace_id": ws, "title": "P", "slug": "attr-proj"},
        **kw,
    ).json()["id"]


# --- auth off (default): byte-identical to pre-16 -----------------------------
def test_local_mode_timeline_has_no_actor_attribution(client):
    pid = _mk_project(client)
    events = client.get(f"/api/v1/projects/{pid}/timeline").json()["events"]
    assert events, "project creation must be audited"
    assert all(e["actor_id"] is None for e in events)
    assert all(e["actor_display"] is None for e in events)


def test_local_mode_approval_decided_by_stays_local(client, session):
    pid = _mk_project(client)
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "T"}
    )
    r = client.post(f"/api/v1/approvals/{ar.id}/approve", headers=_control(client))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decided_by"] == "local"
    assert body["decided_by_display"] is None
    audit = client.get(f"/api/v1/approvals/{ar.id}/audit").json()
    assert all(e["actor_id"] is None for e in audit)
    assert all(e["actor_display"] is None for e in audit)


# --- auth on: the signed-in user is stamped and resolvable --------------------
def test_team_mode_timeline_stamps_the_acting_user(client, auth_on):
    alice = _login(client, "alice@acme.co")
    pid = _mk_project(client, cookies=_auth(alice))
    me = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["user"]

    events = client.get(
        f"/api/v1/projects/{pid}/timeline", cookies=_auth(alice)
    ).json()["events"]
    created = [
        e for e in events if e["entity_type"] == "project" and e["event_type"] == "create"
    ]
    assert created, "project creation must appear on its timeline"
    assert created[0]["actor_id"] == me["id"]
    assert created[0]["actor_display"] == me["display_name"]


def test_team_mode_approver_recorded_and_displayed(client, session, auth_on):
    alice = _login(client, "alice@acme.co")
    pid = _mk_project(client, cookies=_auth(alice))
    me = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["user"]
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "T"}
    )

    r = client.post(
        f"/api/v1/approvals/{ar.id}/approve",
        headers=_control(client),
        cookies=_auth(alice),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decided_by"] == me["id"]
    assert body["decided_by_display"] == me["display_name"]

    # The list read model resolves the display name too.
    listed = client.get(
        f"/api/v1/approvals?project_id={pid}", cookies=_auth(alice)
    ).json()
    assert listed[0]["decided_by_display"] == me["display_name"]

    # And the per-proposal audit trail names the approver on the approve step.
    audit = client.get(f"/api/v1/approvals/{ar.id}/audit", cookies=_auth(alice)).json()
    approved = [e for e in audit if e["event_type"] == "proposal_approved"]
    assert approved and approved[0]["actor_id"] == me["id"]
    assert approved[0]["actor_display"] == me["display_name"]


def test_display_names_degrade_without_auth_tables():
    """A database that has never run the identity migrations (no ``appuser``
    table) must yield no names — never break a canonical read endpoint.
    Regression: the dogfood dev DB (alembic 0024, decided approvals, no auth
    tables) 500'd the approvals list on first deploy of this slice."""
    from sqlmodel import Session, create_engine

    from app.services import audit_service

    engine = create_engine("sqlite://")  # empty DB: no tables at all
    with Session(engine) as bare:
        assert audit_service.display_names(bare, {"usr_x"}) == {}
        # the pre-16 literal never even queries
        assert audit_service.display_names(bare, {"local", None}) == {}


def test_team_mode_rejecter_recorded(client, session, auth_on):
    alice = _login(client, "alice@acme.co")
    pid = _mk_project(client, cookies=_auth(alice))
    me = client.get("/api/v1/auth/me", cookies=_auth(alice)).json()["user"]
    ar = approval_service.create_proposal(
        session, project_id=pid, action_type="task.create", patch={"title": "T"}
    )
    r = client.post(
        f"/api/v1/approvals/{ar.id}/reject",
        headers=_control(client),
        cookies=_auth(alice),
        json={"reason": "not now"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["decided_by"] == me["id"]
    assert r.json()["decided_by_display"] == me["display_name"]
