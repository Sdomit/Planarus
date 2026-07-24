"""Phase 10.1b — real OAuth flow (with a fake provider, no network).

Exercises provider availability gating, the #113 server-side one-time transaction
(binding, replay, expiry, redirect allowlist), verified-email enforcement,
subject-first identity resolution, and the explicit link flow. The built-in
Google/GitHub providers' network calls are not exercised here (they need live
credentials); the flow is provider-agnostic, driven through a fake provider.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from sqlmodel import select

from app.core.config import settings
from app.core.utils import now_utc
from app.models.oauth_transaction import OAuthTransaction
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.services import oauth
from app.services.auth_service import SESSION_COOKIE
from app.services.oauth import OAuthIdentity

COOKIE = SESSION_COOKIE
BINDER = oauth.BINDER_COOKIE
REDIRECT = "https://app/cb"


class _FakeProvider:
    name = "fake"

    def __init__(self, identity):
        self.identity = identity

    def authorize_url(self, state, redirect_uri):
        return f"https://fake.test/authorize?state={state}&redirect_uri={redirect_uri}"

    def exchange_code(self, code, redirect_uri):
        return self.identity


def _identity(**over) -> OAuthIdentity:
    # Routed under "fake", but the identity it returns names a real, allowlisted
    # provider ("github") — the stored UserIdentity.provider must satisfy the CHECK.
    base = dict(
        provider="github",
        subject="sub-123",
        email="Neo@Zion.io",
        display_name="Neo",
        email_verified=True,
    )
    base.update(over)
    return OAuthIdentity(**base)


@pytest.fixture(name="auth_on")
def auth_on_fixture(monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "oauth_redirect_uris", REDIRECT)
    # As elsewhere in the auth tests: the cookies are non-Secure under dev-login,
    # so the TestClient's jar carries them over http like a real browser would.
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    yield


@pytest.fixture(name="fake_oauth")
def fake_oauth_fixture():
    provider = _FakeProvider(_identity())
    oauth.register_test_provider("fake", provider)
    yield provider
    oauth.reset_test_providers()


def _start(client) -> str:
    """Run the start leg and return the state (the binder lands in the jar)."""
    r = client.get(f"/api/v1/auth/oauth/fake/start?redirect_uri={REDIRECT}")
    assert r.status_code == 200, r.text
    return parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]


def _callback(client, state, **kw):
    return client.get(
        "/api/v1/auth/oauth/fake/callback", params={"code": "xyz", "state": state}, **kw
    )


# --- gating -------------------------------------------------------------------
def test_oauth_surface_404_when_auth_off(client, fake_oauth):
    assert client.get("/api/v1/auth/oauth/providers").status_code == 404
    assert client.get(f"/api/v1/auth/oauth/fake/start?redirect_uri={REDIRECT}").status_code == 404


def test_providers_lists_configured(client, auth_on, fake_oauth):
    assert "fake" in client.get("/api/v1/auth/oauth/providers").json()["providers"]


def test_unconfigured_provider_404(client, auth_on):
    assert client.get(f"/api/v1/auth/oauth/google/start?redirect_uri={REDIRECT}").status_code == 404


# --- #113: redirect allowlist -------------------------------------------------
def test_start_refuses_unallowlisted_redirect_uri(client, auth_on, fake_oauth):
    r = client.get("/api/v1/auth/oauth/fake/start?redirect_uri=https://evil.test/cb")
    assert r.status_code == 400


def test_start_refuses_everything_when_allowlist_unset(client, auth_on, fake_oauth, monkeypatch):
    monkeypatch.setattr(settings, "oauth_redirect_uris", "")
    r = client.get(f"/api/v1/auth/oauth/fake/start?redirect_uri={REDIRECT}")
    assert r.status_code == 400


def test_start_sets_binder_cookie_and_returns_url(client, auth_on, fake_oauth):
    r = client.get(f"/api/v1/auth/oauth/fake/start?redirect_uri={REDIRECT}")
    assert r.status_code == 200
    assert r.json()["authorize_url"].startswith("https://fake.test/authorize?state=")
    assert client.cookies.get(BINDER)


# --- #113: the transaction is server-side, one-time and browser-bound ---------
def test_callback_creates_user_and_session(client, auth_on, fake_oauth):
    state = _start(client)
    r = _callback(client, state)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "neo@zion.io"  # normalized
    assert body["user"]["display_name"] == "Neo"
    token = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", cookies={COOKIE: token}).status_code == 200


def test_state_is_stored_server_side_not_signed_into_the_state(client, auth_on, fake_oauth, session):
    """The state carries no payload: the redirect_uri lives only in the row."""
    state = _start(client)
    assert REDIRECT not in state
    row = session.exec(select(OAuthTransaction)).first()
    assert row is not None
    assert row.redirect_uri == REDIRECT and row.kind == "login"
    assert state not in (row.state_hash, row.binder_hash)  # only hashes stored


def test_replayed_state_is_refused(client, auth_on, fake_oauth):
    state = _start(client)
    assert _callback(client, state).status_code == 200
    # The provider redirect (or a log/referrer leak) is replayed a second time.
    assert _callback(client, state).status_code == 400


def test_state_from_another_browser_is_refused(client, auth_on, fake_oauth):
    """Cross-browser transfer: the state without its binder cookie is useless."""
    state = _start(client)
    client.cookies.delete(BINDER)
    assert _callback(client, state).status_code == 400


def test_wrong_binder_is_refused(client, auth_on, fake_oauth):
    state = _start(client)
    client.cookies.set(BINDER, "not-the-binder")
    assert _callback(client, state).status_code == 400


def test_expired_transaction_is_refused(client, auth_on, fake_oauth, session):
    state = _start(client)
    row = session.exec(select(OAuthTransaction)).first()
    row.expires_at = "2000-01-01T00:00:00Z"
    session.add(row)
    session.commit()
    assert _callback(client, state).status_code == 400


def test_concurrent_consumption_has_exactly_one_winner(client, auth_on, fake_oauth, session):
    """Two workers racing the same callback: the conditional UPDATE decides.

    A real second worker is a separate process, but it would run this exact
    statement against this exact row — which is the point of moving the state out
    of process memory.
    """
    state = _start(client)
    binder = client.cookies.get(BINDER)
    first = oauth.consume_transaction(
        session, state=state, binder=binder, kinds=("login",), provider="fake"
    )
    session.commit()
    second = oauth.consume_transaction(
        session, state=state, binder=binder, kinds=("login",), provider="fake"
    )
    session.commit()
    assert first is not None and second is None


def test_calendar_state_cannot_be_used_for_login(client, auth_on, fake_oauth, session):
    """Kind is part of the contract: a calendar transaction is not a login."""
    state, binder = oauth.start_transaction(
        session, kind="calendar", provider="fake", redirect_uri=REDIRECT
    )
    session.commit()
    client.cookies.set(BINDER, binder)
    assert _callback(client, state).status_code == 400


def test_purge_drops_only_expired_transactions(session):
    live, _ = oauth.start_transaction(
        session, kind="login", provider="fake", redirect_uri=REDIRECT
    )
    stale, _ = oauth.start_transaction(
        session, kind="login", provider="fake", redirect_uri=REDIRECT
    )
    session.commit()
    row = session.exec(
        select(OAuthTransaction).where(
            OAuthTransaction.state_hash == oauth.sha256_hex(stale)
        )
    ).first()
    row.expires_at = "2000-01-01T00:00:00Z"
    session.add(row)
    session.commit()
    assert oauth.purge_expired_transactions(session) == 1
    session.commit()
    remaining = session.exec(select(OAuthTransaction)).all()
    assert [r.state_hash for r in remaining] == [oauth.sha256_hex(live)]


def test_bad_state_is_refused(client, auth_on, fake_oauth):
    assert _callback(client, "forged.sig").status_code == 400


# --- #113: verified email only ------------------------------------------------
def test_unverified_email_is_refused(client, auth_on, fake_oauth):
    fake_oauth.identity = _identity(email_verified=False)
    state = _start(client)
    r = _callback(client, state)
    assert r.status_code == 400
    assert "verified" in r.json()["detail"]


def test_missing_email_is_refused(client, auth_on, fake_oauth):
    fake_oauth.identity = _identity(email="", email_verified=True)
    state = _start(client)
    assert _callback(client, state).status_code == 400


# --- #113: subject-first identity resolution ----------------------------------
def test_same_subject_with_a_changed_email_keeps_the_same_account(
    client, auth_on, fake_oauth, session
):
    assert _callback(client, _start(client)).status_code == 200
    first_id = session.exec(select(User)).first().id
    # The provider now reports a different address for the same subject.
    fake_oauth.identity = _identity(email="attacker@evil.test")
    r = _callback(client, _start(client))
    assert r.status_code == 200
    assert r.json()["user"]["id"] == first_id
    assert r.json()["user"]["email"] == "neo@zion.io"  # account email is unchanged
    assert len(session.exec(select(User)).all()) == 1


def test_new_subject_matching_an_existing_email_is_refused(
    client, auth_on, fake_oauth, session
):
    """No silent email-based linking — the takeover path the audit found."""
    assert _callback(client, _start(client)).status_code == 200
    # A different provider account that merely claims the same verified address.
    fake_oauth.identity = _identity(subject="sub-attacker")
    r = _callback(client, _start(client))
    assert r.status_code == 409
    assert len(session.exec(select(UserIdentity)).all()) == 1


# --- #113: the explicit link flow ---------------------------------------------
def test_link_requires_authentication(client, auth_on, fake_oauth):
    assert (
        client.get(f"/api/v1/auth/oauth/fake/link/start?redirect_uri={REDIRECT}").status_code
        == 401
    )


def test_link_attaches_the_new_identity_to_the_signed_in_account(
    client, auth_on, fake_oauth, session
):
    assert _callback(client, _start(client)).status_code == 200  # signed in
    user_id = session.exec(select(User)).first().id
    fake_oauth.identity = _identity(subject="sub-second", email="neo@other.test")
    r = client.get(f"/api/v1/auth/oauth/fake/link/start?redirect_uri={REDIRECT}")
    assert r.status_code == 200
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    assert _callback(client, state).status_code == 200
    subjects = {
        i.provider_subject
        for i in session.exec(select(UserIdentity).where(UserIdentity.user_id == user_id)).all()
    }
    assert subjects == {"sub-123", "sub-second"}
    assert len(session.exec(select(User)).all()) == 1


def test_link_callback_refuses_a_different_signed_in_user(
    client, auth_on, fake_oauth, session
):
    """Callback re-authorization: the opener must still be the one signed in."""
    assert _callback(client, _start(client)).status_code == 200
    r = client.get(f"/api/v1/auth/oauth/fake/link/start?redirect_uri={REDIRECT}")
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    # The browser is now signed in as somebody else (or signed out entirely).
    client.cookies.delete(COOKIE)
    fake_oauth.identity = _identity(subject="sub-second", email="neo@other.test")
    assert _callback(client, state).status_code == 403


def test_link_refuses_an_identity_owned_by_another_account(
    client, auth_on, fake_oauth, session
):
    assert _callback(client, _start(client)).status_code == 200  # user A, sub-123
    first = session.exec(select(User)).first()
    other = User(
        id="usr-other",
        email="trinity@zion.io",
        display_name="Trinity",
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(other)
    session.add(
        UserIdentity(
            id="uid-other",
            user_id=other.id,
            provider="github",
            provider_subject="sub-taken",
            created_at=now_utc(),
        )
    )
    session.commit()
    r = client.get(f"/api/v1/auth/oauth/fake/link/start?redirect_uri={REDIRECT}")
    state = parse_qs(urlparse(r.json()["authorize_url"]).query)["state"][0]
    fake_oauth.identity = _identity(subject="sub-taken", email="trinity@zion.io")
    assert _callback(client, state).status_code == 409
    assert first.id != other.id
