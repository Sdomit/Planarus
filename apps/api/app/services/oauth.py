"""Real OAuth providers + CSRF state (Phase 10.1b).

An `OAuthProvider` turns the authorization-code flow into a normalized
`OAuthIdentity` (provider, subject, email, display_name). Google and GitHub are
built in; a provider is only *available* when its client id is configured (unset →
its routes 404). Secrets are never logged or returned.

The `state` parameter is an HMAC-signed, short-lived token carrying the nonce and
the redirect_uri, so the callback can prove the request originated from our `start`
call (CSRF defense) without server-side session storage. The signing key is
per-process (start→callback happen within one process lifetime), like the local
control token.

Network calls (token + userinfo) use httpx, imported lazily so the default install
doesn't need it — real OAuth requires the optional ``[oauth]`` extra. Tests inject
a fake provider and never hit the network.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.parse import urlencode

from app.core.config import settings

_STATE_SECRET = secrets.token_urlsafe(32)  # per-process; not persisted
_STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str
    display_name: Optional[str]


class OAuthProvider(Protocol):
    name: str

    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthIdentity: ...


# --- signed CSRF state --------------------------------------------------------
def make_state(redirect_uri: str) -> str:
    payload = {
        "nonce": secrets.token_urlsafe(12),
        "redirect_uri": redirect_uri,
        "exp": int(time.time()) + _STATE_TTL_SECONDS,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_state(state: str) -> Optional[str]:
    """Return the redirect_uri if the state is authentic and unexpired, else None."""
    try:
        raw, sig = state.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(_STATE_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload.get("redirect_uri")


# --- built-in providers -------------------------------------------------------
def _httpx():
    try:
        import httpx  # lazy: only needed for real OAuth
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "OAuth requires the optional dependency httpx (install the [oauth] extra)"
        ) from exc
    return httpx


class GoogleOAuthProvider:
    name = "google"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._id, self._secret = client_id, client_secret

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        q = urlencode(
            {
                "client_id": self._id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthIdentity:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": self._id,
                "client_secret": self._secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=15,
        ).json()
        info = httpx.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {tok['access_token']}"},
            timeout=15,
        ).json()
        return OAuthIdentity(
            provider="google",
            subject=str(info["sub"]),
            email=info["email"],
            display_name=info.get("name"),
        )


class GitHubOAuthProvider:
    name = "github"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._id, self._secret = client_id, client_secret

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        q = urlencode(
            {
                "client_id": self._id,
                "redirect_uri": redirect_uri,
                "scope": "read:user user:email",
                "state": state,
            }
        )
        return f"https://github.com/login/oauth/authorize?{q}"

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthIdentity:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "code": code,
                "client_id": self._id,
                "client_secret": self._secret,
                "redirect_uri": redirect_uri,
            },
            timeout=15,
        ).json()
        headers = {
            "Authorization": f"Bearer {tok['access_token']}",
            "Accept": "application/vnd.github+json",
        }
        user = httpx.get("https://api.github.com/user", headers=headers, timeout=15).json()
        email = user.get("email")
        if not email:
            emails = httpx.get(
                "https://api.github.com/user/emails", headers=headers, timeout=15
            ).json()
            primary = next((e for e in emails if e.get("primary")), None)
            email = (primary or (emails[0] if emails else {})).get("email")
        return OAuthIdentity(
            provider="github",
            subject=str(user["id"]),
            email=email,
            display_name=user.get("name") or user.get("login"),
        )


# --- registry -----------------------------------------------------------------
# Tests register fakes here; cleared via reset_test_providers().
_test_providers: dict[str, OAuthProvider] = {}


def register_test_provider(name: str, provider: OAuthProvider) -> None:
    _test_providers[name] = provider


def reset_test_providers() -> None:
    _test_providers.clear()


def get_provider(name: str) -> Optional[OAuthProvider]:
    if name in _test_providers:
        return _test_providers[name]
    if name == "google" and settings.oauth_google_client_id:
        return GoogleOAuthProvider(
            settings.oauth_google_client_id, settings.oauth_google_client_secret
        )
    if name == "github" and settings.oauth_github_client_id:
        return GitHubOAuthProvider(
            settings.oauth_github_client_id, settings.oauth_github_client_secret
        )
    return None


def available_providers() -> list[str]:
    names = set(_test_providers)
    if settings.oauth_google_client_id:
        names.add("google")
    if settings.oauth_github_client_id:
        names.add("github")
    return sorted(names)
