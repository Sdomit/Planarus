"""Phase 11.1 — local email+password provider (D25).

Covers the doubly-gated disabled-by-default surface, create-only registration
(no identity-attach account takeover), generic-401 login, password change with
other-session revocation, the login throttle, and the D26 cookie Secure relax.
Flags flip via monkeypatch (auto-reverted), mirroring test_auth_identity.py.
"""
import pytest
from app.api.v1.endpoints.auth import _pw_limiter
from app.core.config import settings
from app.services import auth_service
from app.services.auth_service import SESSION_COOKIE

COOKIE = SESSION_COOKIE
EMAIL = "pat@team.lan"
PW = "correct horse battery"
PW2 = "staple xkcd rotation"


@pytest.fixture(autouse=True)
def _reset_limiter():
    _pw_limiter.reset()
    yield
    _pw_limiter.reset()


@pytest.fixture(name="pw_on")
def pw_on_fixture(monkeypatch):
    """Auth + the password provider on; dev-login stays OFF (D25: never loosened)."""
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_password_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", False)
    yield


def _register(client, email=EMAIL, password=PW, display_name=None):
    body = {"email": email, "password": password}
    if display_name:
        body["display_name"] = display_name
    return client.post("/api/v1/auth/password/register", json=body)


def _login(client, email=EMAIL, password=PW):
    return client.post(
        "/api/v1/auth/password/login", json={"email": email, "password": password}
    )


def _token(client) -> str:
    token = client.cookies.get(COOKIE)
    assert token
    client.cookies.clear()
    return token


def _auth(token):
    return {COOKIE: token}


# --- disabled by default (double gate) ----------------------------------------
def test_password_surface_404_when_auth_disabled(client):
    assert _register(client).status_code == 404
    assert _login(client).status_code == 404
    assert (
        client.post(
            "/api/v1/auth/password/change",
            json={"current_password": PW, "new_password": PW2},
        ).status_code
        == 404
    )


def test_password_surface_404_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_password_enabled", False)
    assert _register(client).status_code == 404
    assert _login(client).status_code == 404


# --- register -------------------------------------------------------------------
def test_register_login_me_flow(client, pw_on):
    r = _register(client, email="Pat@Team.LAN", display_name="Pat")
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "pat@team.lan"  # normalized
    assert body["user"]["display_name"] == "Pat"
    assert body["memberships"] == []
    token = _token(client)

    me = client.get("/api/v1/auth/me", cookies=_auth(token))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "pat@team.lan"

    # A fresh login with the same credentials works too.
    assert _login(client).status_code == 200


def test_register_is_create_only_no_takeover(client, pw_on):
    assert _register(client).status_code == 201
    client.cookies.clear()
    # Second register on the same email (attacker picks their own password) → 409,
    # and the original password still logs in.
    r = _register(client, password="attacker password 1")
    assert r.status_code == 409
    assert _login(client, password="attacker password 1").status_code == 401
    client.cookies.clear()
    assert _login(client).status_code == 200


def test_register_conflicts_with_existing_provider_account(client, session, pw_on):
    # An account that exists via another provider (dev here) can NOT be claimed
    # by an unauthenticated register with the same email.
    auth_service.login_with_identity(session, "dev", EMAIL, EMAIL, "Dev Pat")
    r = _register(client)
    assert r.status_code == 409


def test_register_weak_password_422(client, pw_on):
    assert _register(client, password="short").status_code == 422


# --- login ----------------------------------------------------------------------
def test_login_failures_are_generic_401(client, pw_on):
    assert _register(client).status_code == 201
    client.cookies.clear()
    wrong = _login(client, password="wrong password 42")
    unknown = _login(client, email="nobody@team.lan")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_login_inactive_user_401(client, session, pw_on):
    assert _register(client).status_code == 201
    client.cookies.clear()
    user = auth_service.user_by_email(session, EMAIL)
    user.is_active = False
    session.add(user)
    session.commit()
    assert _login(client).status_code == 401


def test_login_rate_limited_429(client, pw_on):
    assert _register(client).status_code == 201
    client.cookies.clear()
    for _ in range(10):  # ten attempts fill the 10/min window (register doesn't count)
        assert _login(client, password="wrong password 42").status_code == 401
    r = _login(client, password="wrong password 42")
    assert r.status_code == 429
    assert "Retry-After" in r.headers
    # Another email is unaffected (per-email bucket).
    assert _login(client, email="other@team.lan").status_code == 401


# --- change password ------------------------------------------------------------
def test_change_password_flow(client, pw_on):
    assert _register(client).status_code == 201
    token = _token(client)

    wrong = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "not the password", "new_password": PW2},
        cookies=_auth(token),
    )
    assert wrong.status_code == 400

    ok = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PW, "new_password": PW2},
        cookies=_auth(token),
    )
    assert ok.status_code == 204

    assert _login(client).status_code == 401  # old password dead
    client.cookies.clear()
    assert _login(client, password=PW2).status_code == 200  # new one works
    # The caller's own session survived the rotation.
    assert client.get("/api/v1/auth/me", cookies=_auth(token)).status_code == 200


def test_change_password_revokes_other_sessions(client, pw_on):
    assert _register(client).status_code == 201
    token_a = _token(client)
    assert _login(client).status_code == 200
    token_b = _token(client)

    ok = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PW, "new_password": PW2},
        cookies=_auth(token_a),
    )
    assert ok.status_code == 204
    assert client.get("/api/v1/auth/me", cookies=_auth(token_a)).status_code == 200
    assert client.get("/api/v1/auth/me", cookies=_auth(token_b)).status_code == 401


def test_change_password_requires_password_identity(client, session, pw_on, monkeypatch):
    # A dev-provider account has no password identity → 409 (out of P11.1 scope).
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    r = client.post("/api/v1/auth/dev-login", json={"email": "oauthish@team.lan"})
    assert r.status_code == 200
    token = _token(client)
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "irrelevant pw", "new_password": PW2},
        cookies=_auth(token),
    )
    assert r.status_code == 409


def test_change_password_requires_login(client, pw_on):
    r = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": PW, "new_password": PW2},
    )
    assert r.status_code == 401


# --- hygiene --------------------------------------------------------------------
def test_no_hash_material_in_responses(client, pw_on):
    r = _register(client)
    assert r.status_code == 201
    for text in (r.text, str(dict(r.headers))):
        assert "argon2" not in text
        assert "password_hash" not in text
    token = _token(client)
    me = client.get("/api/v1/auth/me", cookies=_auth(token))
    # P16.1: the boolean must-change flag is the one sanctioned "password"
    # occurrence — strip exactly it, then keep the blanket guard at full strength.
    scrubbed = me.text.replace('"password_must_change":false', "").replace(
        '"password_must_change":true', ""
    )
    assert "password" not in scrubbed


def test_cookie_secure_relaxed_for_lan_mode(client, pw_on, monkeypatch):
    # Hosted posture (dev off, LAN off): Secure cookie.
    r = _register(client)
    assert r.status_code == 201
    assert "secure" in r.headers["set-cookie"].lower()
    client.cookies.clear()
    # D26: LAN mode is plain HTTP by ratified decision — Secure would brick login.
    monkeypatch.setattr(settings, "lan_mode_enabled", True)
    r = _login(client)
    assert r.status_code == 200
    assert "secure" not in r.headers["set-cookie"].lower()
