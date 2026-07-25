from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from app.core.config import settings
from app.services import calendar_sync, oauth
from app.services.auth_service import SESSION_COOKIE
from app.services.calendar_sync import CalendarTokens, RemoteEvent
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-sync"}).json()
    proj = client.post(
        "/api/v1/projects", json={"workspace_id": ws["id"], "title": "P", "slug": "p-sync"}
    ).json()
    return ws["id"], proj["id"]


class FakeBackend:
    name = "google"

    def __init__(self) -> None:
        self.created: list = []
        self.remotes: list[RemoteEvent] = []

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return "https://fake/auth?" + urlencode({"state": state, "redirect_uri": redirect_uri})

    def exchange_code(self, code: str, redirect_uri: str) -> CalendarTokens:
        return CalendarTokens(access_token="at", refresh_token="rt", expiry=None,
                              email="you@example.com", scope="s")

    def refresh(self, refresh_token: str) -> CalendarTokens:
        return CalendarTokens(access_token="at2", refresh_token=refresh_token, expiry=None, email="", scope="s")

    def list_events(self, access_token, sync_token):
        return self.remotes, "synctoken-1"

    def create_event(self, access_token, ev):
        rid = f"remote-{len(self.created)}"
        self.created.append(ev)
        return RemoteEvent(external_uid=rid, etag="e1", title=ev.title,
                           start_at=ev.start_at, end_at=ev.end_at, all_day=ev.all_day)

    def delete_event(self, access_token, external_uid):
        pass


CALLBACK_URI = "http://localhost:8000/cb"


@pytest.fixture
def sync_enabled():
    """Turn on encryption + register a fake 'google' backend for the test."""
    prev = settings.calendar_enc_key
    prev_uris = settings.oauth_redirect_uris
    settings.calendar_enc_key = Fernet.generate_key().decode()
    # #113: connect refuses any redirect_uri outside the configured allowlist.
    settings.oauth_redirect_uris = CALLBACK_URI
    fake = FakeBackend()
    calendar_sync.register_test_backend("google", fake)
    yield fake
    calendar_sync.reset_test_backends()
    settings.calendar_enc_key = prev
    settings.oauth_redirect_uris = prev_uris


def _connect(client: TestClient, pid: str) -> str:
    """Drive connect→callback with the fake, returning the new connection id."""
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": CALLBACK_URI})
    assert r.status_code == 200
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    cb = client.get("/api/v1/calendar-sync/google/callback", params={"code": "abc", "state": state})
    assert cb.status_code == 200
    return client.get(f"/api/v1/projects/{pid}/calendar-connections").json()[0]["id"]


# ── Disabled by default ────────────────────────────────────────────────────
def test_sync_disabled_without_config(client: TestClient) -> None:
    _, pid = _seed(client)
    assert client.get("/api/v1/calendar-sync/providers").json()["providers"] == []
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": "x"})
    assert r.status_code == 404  # provider not configured → gated off


def test_token_crypto_roundtrip() -> None:
    from app.core import token_crypto
    prev = settings.calendar_enc_key
    settings.calendar_enc_key = Fernet.generate_key().decode()
    try:
        assert token_crypto.is_enabled()
        enc = token_crypto.encrypt("secret-token")
        assert enc != "secret-token"
        assert token_crypto.decrypt(enc) == "secret-token"
    finally:
        settings.calendar_enc_key = prev


# ── Connect / callback ─────────────────────────────────────────────────────
def test_provider_available_when_enabled(client: TestClient, sync_enabled) -> None:
    assert client.get("/api/v1/calendar-sync/providers").json()["providers"] == ["google"]


def test_connect_and_callback_creates_connection(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    conn_id = _connect(client, pid)
    lst = client.get(f"/api/v1/projects/{pid}/calendar-connections").json()
    assert len(lst) == 1
    row = lst[0]
    assert row["id"] == conn_id
    assert row["provider"] == "google"
    assert row["account_email"] == "you@example.com"
    assert row["status"] == "connected"
    # Never expose tokens.
    assert "access_token" not in row and "access_token_enc" not in row and "refresh_token_enc" not in row


def test_callback_rejects_tampered_state(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    cb = client.get("/api/v1/calendar-sync/google/callback",
                    params={"code": "abc", "state": "not-a-valid-state"})
    assert cb.status_code == 400


def test_connect_refuses_unallowlisted_redirect_uri(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": "https://evil.test/cb"})
    assert r.status_code == 400


def test_callback_state_is_one_time(client: TestClient, sync_enabled) -> None:
    """#113: a replayed callback cannot attach a second connection."""
    _, pid = _seed(client)
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": CALLBACK_URI})
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    assert client.get("/api/v1/calendar-sync/google/callback",
                      params={"code": "abc", "state": state}).status_code == 200
    assert client.get("/api/v1/calendar-sync/google/callback",
                      params={"code": "abc", "state": state}).status_code == 400
    assert len(client.get(f"/api/v1/projects/{pid}/calendar-connections").json()) == 1


def test_callback_without_the_binder_cookie_is_refused(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": CALLBACK_URI})
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    client.cookies.delete(oauth.BINDER_COOKIE)
    cb = client.get("/api/v1/calendar-sync/google/callback",
                    params={"code": "abc", "state": state})
    assert cb.status_code == 400
    assert client.get(f"/api/v1/projects/{pid}/calendar-connections").json() == []


# ── #113: the callback re-authorizes (tenant_guard cannot see it) ───────────
@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


def _login(client: TestClient, email: str) -> str:
    assert client.post("/api/v1/auth/dev-login", json={"email": email}).status_code == 200
    token = client.cookies.get(SESSION_COOKIE)
    client.cookies.clear()
    return token


def _owned_project(client: TestClient, token: str) -> tuple[str, str]:
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": "ws-auth"},
                     cookies={SESSION_COOKIE: token}).json()["id"]
    pid = client.post("/api/v1/projects",
                      json={"workspace_id": ws, "title": "P", "slug": "p-auth"},
                      cookies={SESSION_COOKIE: token}).json()["id"]
    return ws, pid


def _start_connect(client: TestClient, pid: str, token: str) -> tuple[str, str]:
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": CALLBACK_URI},
                   cookies={SESSION_COOKIE: token})
    assert r.status_code == 200, r.text
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    binder = client.cookies.get(oauth.BINDER_COOKIE)
    client.cookies.clear()
    return state, binder


def test_callback_refuses_a_different_user(client: TestClient, sync_enabled, auth_on) -> None:
    """The audit's cross-tenant token attachment: another account finishing the
    flow must not bind the provider's calendar to the opener's project."""
    alice = _login(client, "alice@acme.co")
    mallory = _login(client, "mallory@evil.test")
    _, pid = _owned_project(client, alice)
    state, binder = _start_connect(client, pid, alice)
    cb = client.get("/api/v1/calendar-sync/google/callback",
                    params={"code": "abc", "state": state},
                    cookies={SESSION_COOKIE: mallory, oauth.BINDER_COOKIE: binder})
    assert cb.status_code == 403
    lst = client.get(f"/api/v1/projects/{pid}/calendar-connections",
                     cookies={SESSION_COOKIE: alice})
    assert lst.json() == []


def test_callback_accepts_the_opener(client: TestClient, sync_enabled, auth_on) -> None:
    alice = _login(client, "alice@acme.co")
    _, pid = _owned_project(client, alice)
    state, binder = _start_connect(client, pid, alice)
    cb = client.get("/api/v1/calendar-sync/google/callback",
                    params={"code": "abc", "state": state},
                    cookies={SESSION_COOKIE: alice, oauth.BINDER_COOKIE: binder})
    assert cb.status_code == 200, cb.text
    lst = client.get(f"/api/v1/projects/{pid}/calendar-connections",
                     cookies={SESSION_COOKIE: alice})
    assert len(lst.json()) == 1


def test_connect_requires_a_write_role(client: TestClient, sync_enabled, auth_on) -> None:
    """Connect is a GET, so tenant_guard only enforced the READ roles."""
    alice = _login(client, "alice@acme.co")
    bob = _login(client, "bob@acme.co")
    ws, pid = _owned_project(client, alice)
    client.post(f"/api/v1/workspaces/{ws}/members",
                json={"email": "bob@acme.co", "role": "viewer"},
                cookies={SESSION_COOKIE: alice})
    r = client.get("/api/v1/calendar-sync/google/connect",
                   params={"project_id": pid, "redirect_uri": CALLBACK_URI},
                   cookies={SESSION_COOKIE: bob})
    assert r.status_code == 403


def test_disconnect_removes_connection(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    conn_id = _connect(client, pid)
    assert client.delete(f"/api/v1/calendar-connections/{conn_id}").status_code == 204
    assert client.get(f"/api/v1/projects/{pid}/calendar-connections").json() == []


# ── Sync push + pull ───────────────────────────────────────────────────────
def test_sync_pushes_local_and_pulls_remote(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    conn_id = _connect(client, pid)
    # One un-synced local event to push.
    client.post(f"/api/v1/projects/{pid}/calendar-events",
                json={"title": "Local", "start_at": "2026-08-01", "all_day": True})
    # One remote event to pull.
    sync_enabled.remotes = [RemoteEvent(external_uid="rmt-1", etag="e9", title="Remote",
                                        start_at="2026-08-05", end_at=None, all_day=True)]

    res = client.post(f"/api/v1/calendar-connections/{conn_id}/sync")
    assert res.status_code == 200
    body = res.json()
    assert body["pushed"] == 1
    assert body["pulled"] == 1
    assert body["status"] == "connected"

    # Local pushed to the fake; remote materialized locally.
    assert len(sync_enabled.created) == 1 and sync_enabled.created[0].title == "Local"
    titles = {e["title"] for e in client.get(f"/api/v1/projects/{pid}/calendar-events").json()}
    assert {"Local", "Remote"} <= titles


def test_sync_is_idempotent_second_run_pushes_nothing(client: TestClient, sync_enabled) -> None:
    _, pid = _seed(client)
    conn_id = _connect(client, pid)
    client.post(f"/api/v1/projects/{pid}/calendar-events",
                json={"title": "Local", "start_at": "2026-08-01", "all_day": True})
    client.post(f"/api/v1/calendar-connections/{conn_id}/sync")
    # Second sync: the event now carries an external_uid, so it isn't re-pushed.
    second = client.post(f"/api/v1/calendar-connections/{conn_id}/sync").json()
    assert second["pushed"] == 0
