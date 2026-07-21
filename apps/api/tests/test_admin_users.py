"""Phase 16.1 — admin core (D29/D30/D31/D34/D35).

The admin plane: 404 when auth is off; session + server-admin + control token
on mutations; first-user bootstrap; temp-password lifecycle (must-change,
session revocation); last-active-admin guards; the registration switch; and
the D35 settings hardening.
"""
import pytest

from app.core.config import settings
from app.services.auth_service import SESSION_COOKIE


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    monkeypatch.setattr(settings, "auth_password_enabled", True)
    yield


def _login(client, email) -> str:
    r = client.post("/api/v1/auth/dev-login", json={"email": email})
    assert r.status_code == 200, r.text
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    return token


def _pw_login(client, email, password) -> tuple[int, str]:
    r = client.post(
        "/api/v1/auth/password/login", json={"email": email, "password": password}
    )
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    return r.status_code, token


def _auth(token):
    return {SESSION_COOKIE: token}


def _control(client) -> dict:
    return {
        "X-Planarus-Local-Token": client.get("/api/v1/local-session").json()["token"]
    }


# --- surface gating -----------------------------------------------------------
def test_admin_surface_404_when_auth_off(client):
    assert client.get("/api/v1/admin/users").status_code == 404


def test_first_user_bootstraps_to_admin(client, auth_on):
    first = _login(client, "root@acme.co")
    second = _login(client, "user@acme.co")
    me1 = client.get("/api/v1/auth/me", cookies=_auth(first)).json()["user"]
    me2 = client.get("/api/v1/auth/me", cookies=_auth(second)).json()["user"]
    assert me1["is_admin"] is True
    assert me2["is_admin"] is False


def test_auth_status_flags_unclaimed_server(client, auth_on):
    """The first-run signal: true before anyone registers, false after."""
    assert client.get("/api/v1/auth/status").json() == {"needs_setup": True}
    _login(client, "root@acme.co")
    assert client.get("/api/v1/auth/status").json() == {"needs_setup": False}


def test_auth_status_404_when_auth_off(client):
    assert client.get("/api/v1/auth/status").status_code == 404


def test_roster_admin_only(client, auth_on):
    admin = _login(client, "root@acme.co")
    plain = _login(client, "user@acme.co")
    assert client.get("/api/v1/admin/users", cookies=_auth(plain)).status_code == 403
    roster = client.get("/api/v1/admin/users", cookies=_auth(admin))
    assert roster.status_code == 200
    rows = roster.json()
    assert {u["email"] for u in rows} == {"root@acme.co", "user@acme.co"}
    by_email = {u["email"]: u for u in rows}
    assert by_email["root@acme.co"]["is_admin"] is True
    # both signed in via resolve → last_seen stamped
    assert by_email["user@acme.co"]["last_seen_at"]


def test_mutations_need_control_token(client, auth_on):
    admin = _login(client, "root@acme.co")
    r = client.post(
        "/api/v1/admin/users",
        json={"email": "new@acme.co"},
        cookies=_auth(admin),
    )
    assert r.status_code == 401  # valid admin session, missing control token


# --- temp-password lifecycle --------------------------------------------------
def test_admin_creates_user_with_temp_password_and_forced_change(client, auth_on):
    admin = _login(client, "root@acme.co")
    r = client.post(
        "/api/v1/admin/users",
        json={"email": "new@acme.co", "display_name": "New Person"},
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    temp = body["temp_password"]
    assert len(temp) >= 10
    assert body["user"]["is_admin"] is False

    # duplicate email → 409 (create-only rule holds for admins too)
    dup = client.post(
        "/api/v1/admin/users",
        json={"email": "new@acme.co"},
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert dup.status_code == 409

    # the temp password signs in, but the session is fenced to the auth surface
    code, tok = _pw_login(client, "new@acme.co", temp)
    assert code == 200
    me = client.get("/api/v1/auth/me", cookies=_auth(tok)).json()
    assert me["password_must_change"] is True
    assert client.get("/api/v1/projects", cookies=_auth(tok)).status_code == 403

    # rotating the password clears the fence
    ch = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": temp, "new_password": "a-real-password-1"},
        cookies=_auth(tok),
    )
    assert ch.status_code == 204, ch.text
    assert client.get("/api/v1/projects", cookies=_auth(tok)).status_code == 200
    me2 = client.get("/api/v1/auth/me", cookies=_auth(tok)).json()
    assert me2["password_must_change"] is False


def test_admin_created_user_can_be_granted_access_immediately(client, session, auth_on):
    """The Team UI's one-step "Add user": create the account, then grant it
    workspace access using the email the create response returns.

    Pins the two things that flow depends on — a brand-new account resolves by
    email right away (no "sign in once first"), and the grant outlives the
    forced password rotation, so the access the admin was promised is really
    there when the person arrives.
    """
    from app.schemas.workspace import WorkspaceCreate
    from app.services import workspace_service

    ws = workspace_service.create_workspace(
        session, WorkspaceCreate(name="Studio", slug="studio")
    ).id
    admin = _login(client, "root@acme.co")
    claim = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": "root@acme.co", "role": "owner"},
        cookies=_auth(admin),
    )
    assert claim.status_code == 201, claim.text

    created = client.post(
        "/api/v1/admin/users",
        json={"email": "Sam@Acme.CO"},
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    # the UI grants with the RESPONSE's email, not the raw input — so the
    # server's normalization is part of the contract it relies on.
    email = body["user"]["email"]
    assert email == "sam@acme.co"

    granted = client.post(
        f"/api/v1/workspaces/{ws}/members",
        json={"email": email, "role": "viewer"},
        cookies=_auth(admin),
    )
    assert granted.status_code == 201, granted.text
    assert granted.json()["role"] == "viewer"

    code, tok = _pw_login(client, email, body["temp_password"])
    assert code == 200
    rotate = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": body["temp_password"], "new_password": "a-real-password-1"},
        cookies=_auth(tok),
    )
    assert rotate.status_code == 204, rotate.text
    me = client.get("/api/v1/auth/me", cookies=_auth(tok)).json()
    assert (ws, "viewer") in {(m["workspace_id"], m["role"]) for m in me["memberships"]}
    roster = client.get(f"/api/v1/workspaces/{ws}/members", cookies=_auth(tok))
    assert roster.status_code == 200
    assert email in {m["email"] for m in roster.json()}


def test_admin_reset_password_revokes_sessions(client, auth_on):
    admin = _login(client, "root@acme.co")
    create = client.post(
        "/api/v1/admin/users",
        json={"email": "vic@acme.co"},
        headers=_control(client),
        cookies=_auth(admin),
    ).json()
    _, old_tok = _pw_login(client, "vic@acme.co", create["temp_password"])
    uid = create["user"]["id"]

    r = client.post(
        f"/api/v1/admin/users/{uid}/reset-password",
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert r.status_code == 200, r.text
    new_temp = r.json()["temp_password"]
    # every prior session is dead; the new temp signs in with the fence up
    assert client.get("/api/v1/auth/me", cookies=_auth(old_tok)).status_code == 401
    code, tok = _pw_login(client, "vic@acme.co", new_temp)
    assert code == 200
    assert client.get("/api/v1/auth/me", cookies=_auth(tok)).json()[
        "password_must_change"
    ]


def test_reset_refuses_accounts_without_password_login(client, auth_on):
    admin = _login(client, "root@acme.co")
    dev_only = _login(client, "devonly@acme.co")
    uid = client.get("/api/v1/auth/me", cookies=_auth(dev_only)).json()["user"]["id"]
    r = client.post(
        f"/api/v1/admin/users/{uid}/reset-password",
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert r.status_code == 409  # anti-takeover: never attach a first password


# --- deactivate / reactivate / admin flag ------------------------------------
def test_deactivate_revokes_and_blocks_login_reactivate_restores(client, auth_on):
    admin = _login(client, "root@acme.co")
    create = client.post(
        "/api/v1/admin/users",
        json={"email": "leaver@acme.co"},
        headers=_control(client),
        cookies=_auth(admin),
    ).json()
    temp = create["temp_password"]
    uid = create["user"]["id"]
    _, live = _pw_login(client, "leaver@acme.co", temp)

    r = client.post(
        f"/api/v1/admin/users/{uid}/deactivate",
        headers=_control(client),
        cookies=_auth(admin),
    )
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.get("/api/v1/auth/me", cookies=_auth(live)).status_code == 401
    code, _ = _pw_login(client, "leaver@acme.co", temp)
    assert code == 401  # is_active honored at login, same generic error

    client.post(
        f"/api/v1/admin/users/{uid}/reactivate",
        headers=_control(client),
        cookies=_auth(admin),
    )
    code, _ = _pw_login(client, "leaver@acme.co", temp)
    assert code == 200


def test_last_active_admin_guards(client, auth_on):
    admin = _login(client, "root@acme.co")
    uid = client.get("/api/v1/auth/me", cookies=_auth(admin)).json()["user"]["id"]
    hdr = _control(client)

    # sole admin: cannot demote or deactivate
    assert (
        client.patch(
            f"/api/v1/admin/users/{uid}",
            json={"is_admin": False},
            headers=hdr,
            cookies=_auth(admin),
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/admin/users/{uid}/deactivate", headers=hdr, cookies=_auth(admin)
        ).status_code
        == 409
    )

    # grant a second admin → demoting the first now works
    other = _login(client, "second@acme.co")
    oid = client.get("/api/v1/auth/me", cookies=_auth(other)).json()["user"]["id"]
    assert (
        client.patch(
            f"/api/v1/admin/users/{oid}",
            json={"is_admin": True},
            headers=hdr,
            cookies=_auth(admin),
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/api/v1/admin/users/{uid}",
            json={"is_admin": False},
            headers=hdr,
            cookies=_auth(admin),
        ).status_code
        == 200
    )


# --- registration switch (D30) ------------------------------------------------
def test_registration_switch_closes_the_door(client, session, auth_on):
    from app.services import settings_service

    r = client.post(
        "/api/v1/auth/password/register",
        json={"email": "open@acme.co", "password": "longenough-1"},
    )
    assert r.status_code == 201  # default: open, today's behavior
    client.cookies.clear()

    settings_service.set_setting(session, "registration_open", False)
    session.commit()
    r2 = client.post(
        "/api/v1/auth/password/register",
        json={"email": "closed@acme.co", "password": "longenough-1"},
    )
    assert r2.status_code == 404  # indistinguishable from a disabled surface

    # admin-created accounts remain the controlled path
    admin_tok = _pw_login(client, "open@acme.co", "longenough-1")[1]
    # (first account on the server → bootstrap admin)
    r3 = client.post(
        "/api/v1/admin/users",
        json={"email": "closed@acme.co"},
        headers=_control(client),
        cookies=_auth(admin_tok),
    )
    assert r3.status_code == 201


# --- D35: settings hardening --------------------------------------------------
def test_settings_put_requires_admin_in_team_mode(client, auth_on):
    admin = _login(client, "root@acme.co")
    plain = _login(client, "user@acme.co")
    hdr = _control(client)

    denied = client.put(
        "/api/v1/settings",
        json={"registration_open": False},
        headers=hdr,
        cookies=_auth(plain),
    )
    assert denied.status_code == 403

    ok = client.put(
        "/api/v1/settings",
        json={"registration_open": False},
        headers=hdr,
        cookies=_auth(admin),
    )
    assert ok.status_code == 200
    assert ok.json()["registration_open"] is False
