"""Phase 10.1b — real OAuth flow (with a fake provider, no network).

Exercises provider availability gating, the signed-state CSRF check, and the
start→callback flow creating a user + session. The built-in Google/GitHub
providers' network calls are not exercised here (they need live credentials);
the flow is provider-agnostic, driven through a fake provider.
"""
import pytest

from app.core.config import settings
from app.services import oauth
from app.services.auth_service import SESSION_COOKIE
from app.services.oauth import OAuthIdentity

COOKIE = SESSION_COOKIE


class _FakeProvider:
    name = "fake"

    def __init__(self, identity):
        self._identity = identity

    def authorize_url(self, state, redirect_uri):
        return f"https://fake.test/authorize?state={state}&redirect_uri={redirect_uri}"

    def exchange_code(self, code, redirect_uri):
        return self._identity


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    yield


@pytest.fixture(name="fake_oauth")
def fake_oauth_fixture():
    # Routed under "fake", but the identity it returns names a real, allowlisted
    # provider ("github") — the stored UserIdentity.provider must satisfy the CHECK.
    oauth.register_test_provider(
        "fake",
        _FakeProvider(
            OAuthIdentity(provider="github", subject="sub-123", email="Neo@Zion.io", display_name="Neo")
        ),
    )
    yield
    oauth.reset_test_providers()


def test_oauth_surface_404_when_auth_off(client, fake_oauth):
    assert client.get("/api/v1/auth/oauth/providers").status_code == 404
    assert client.get("/api/v1/auth/oauth/fake/start?redirect_uri=https://a/cb").status_code == 404


def test_providers_lists_configured(client, auth_on, fake_oauth):
    body = client.get("/api/v1/auth/oauth/providers").json()
    assert "fake" in body["providers"]


def test_unconfigured_provider_404(client, auth_on):
    assert client.get("/api/v1/auth/oauth/google/start?redirect_uri=https://a/cb").status_code == 404


def test_start_returns_authorize_url(client, auth_on, fake_oauth):
    r = client.get("/api/v1/auth/oauth/fake/start?redirect_uri=https://app/cb")
    assert r.status_code == 200
    assert r.json()["authorize_url"].startswith("https://fake.test/authorize?state=")


def test_callback_creates_user_and_session(client, auth_on, fake_oauth):
    state = oauth.make_state("https://app/cb")
    r = client.get(f"/api/v1/auth/oauth/fake/callback?code=xyz&state={state}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "neo@zion.io"  # normalized
    assert body["user"]["display_name"] == "Neo"
    # the session cookie works
    token = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", cookies={COOKIE: token}).status_code == 200


def test_callback_rejects_bad_state(client, auth_on, fake_oauth):
    assert (
        client.get("/api/v1/auth/oauth/fake/callback?code=xyz&state=forged.sig").status_code
        == 400
    )


def test_state_roundtrip_and_tamper():
    state = oauth.make_state("https://app/cb")
    assert oauth.verify_state(state) == "https://app/cb"
    assert oauth.verify_state(state + "x") is None
    assert oauth.verify_state("garbage") is None
