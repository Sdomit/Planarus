"""Real OAuth providers + server-side one-time transactions (Phase 10.1b, #113).

An `OAuthProvider` turns the authorization-code flow into a normalized
`OAuthIdentity` (provider, subject, email, email_verified, display_name). Google
and GitHub are built in; a provider is only *available* when its client id is
configured (unset → its routes 404). Secrets are never logged or returned.

The `state` parameter used to be an HMAC blob signed with a per-process key and
carrying the caller-supplied redirect_uri: transferable between browsers,
replayable until expiry, and invisible to a second worker. It is now an opaque
random token whose hash is one row in `oauthtransaction`, created by `start` and
consumed exactly once by the callback (#113). Every transaction is additionally
bound to a `binder` value that the browser holds in a short-lived HttpOnly
cookie, so a state stolen out of a URL/log/referrer is useless in another
browser, and the redirect_uri comes from a configured allowlist rather than the
caller.

Network calls (token + userinfo) use httpx, imported lazily so the default install
doesn't need it — real OAuth requires the optional ``[oauth]`` extra. Tests inject
a fake provider and never hit the network.
"""
from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.parse import urlencode

from sqlalchemy import update as sa_update
from sqlmodel import Session, select

from app.core.config import settings
from app.core.utils import new_id, now_utc, now_utc_plus_hours, sha256_hex
from app.models.oauth_transaction import OAuthTransaction

STATE_TTL_SECONDS = 600
BINDER_COOKIE = "planarus_oauth_binder"

TRANSACTION_KINDS = ("login", "link", "calendar")


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str
    display_name: Optional[str]
    # #113: only a provider-verified email may create or resolve an account. The
    # default is False so a provider adapter has to opt in deliberately.
    email_verified: bool = False


class OAuthProvider(Protocol):
    name: str

    def authorize_url(self, state: str, redirect_uri: str) -> str: ...

    def exchange_code(self, code: str, redirect_uri: str) -> OAuthIdentity: ...


# --- redirect allowlist -------------------------------------------------------
def allowed_redirect_uris() -> list[str]:
    return [u.strip() for u in settings.oauth_redirect_uris.split(",") if u.strip()]


def is_allowed_redirect_uri(redirect_uri: str) -> bool:
    """Exact membership in the configured allowlist. Fail-closed: an unset
    allowlist allows nothing, so no flow can start with a caller-chosen URL."""
    return redirect_uri in allowed_redirect_uris()


# --- server-side one-time transactions ----------------------------------------
def start_transaction(
    session: Session,
    *,
    kind: str,
    provider: str,
    redirect_uri: str,
    user_id: Optional[str] = None,
    project_id: Optional[str] = None,
) -> tuple[str, str]:
    """Open a one-time transaction; return ``(state, binder)``.

    ``state`` goes to the provider in the authorization URL, ``binder`` into a
    short-lived cookie on the initiating browser. Only their hashes are stored.
    Caller commits.
    """
    if kind not in TRANSACTION_KINDS:  # pragma: no cover - programming error
        raise ValueError(f"unknown transaction kind {kind!r}")
    state = new_id("oas") + "." + secrets.token_urlsafe(24)
    binder = secrets.token_urlsafe(24)
    session.add(
        OAuthTransaction(
            id=new_id("oatx"),
            kind=kind,
            provider=provider,
            state_hash=sha256_hex(state),
            binder_hash=sha256_hex(binder),
            redirect_uri=redirect_uri,
            user_id=user_id,
            project_id=project_id,
            created_at=now_utc(),
            expires_at=now_utc_plus_hours(STATE_TTL_SECONDS / 3600),
        )
    )
    return state, binder


def consume_transaction(
    session: Session,
    *,
    state: Optional[str],
    binder: Optional[str],
    kinds: tuple[str, ...],
    provider: str,
) -> Optional[OAuthTransaction]:
    """Atomically claim a transaction, or return None.

    The claim is a single conditional UPDATE on ``consumed_at``, so a replayed
    callback — or a second worker racing the first — loses: exactly one caller
    ever sees the row. Only then are the cheap checks (expiry, kind, provider,
    binder) applied, and a failure leaves the transaction consumed rather than
    reopening it for another guess. Caller commits.
    """
    if not state or not binder:
        return None
    claimed_at = now_utc()
    result = session.execute(
        sa_update(OAuthTransaction)
        .where(
            OAuthTransaction.state_hash == sha256_hex(state),
            OAuthTransaction.consumed_at.is_(None),
        )
        .values(consumed_at=claimed_at)
    )
    if result.rowcount != 1:
        return None
    txn = session.exec(
        select(OAuthTransaction).where(
            OAuthTransaction.state_hash == sha256_hex(state)
        )
    ).first()
    if txn is None:  # pragma: no cover - the UPDATE just matched it
        return None
    if txn.consumed_at != claimed_at:  # pragma: no cover - defensive
        return None
    if txn.expires_at <= now_utc():
        return None
    if txn.kind not in kinds or txn.provider != provider:
        return None
    if not hmac.compare_digest(txn.binder_hash, sha256_hex(binder)):
        return None
    return txn


def purge_expired_transactions(session: Session) -> int:
    """Drop transactions past their expiry. Called opportunistically on start so
    the table stays bounded without a scheduler. Caller commits.

    ponytail: a delete-on-write sweep, not a background job — the table only
    grows at the rate people click "sign in".
    """
    rows = session.exec(
        select(OAuthTransaction).where(OAuthTransaction.expires_at <= now_utc())
    ).all()
    for row in rows:
        session.delete(row)
    return len(rows)


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
            email=info.get("email") or "",
            display_name=info.get("name"),
            # #113: Google returns email_verified as a bool or the string "true".
            email_verified=str(info.get("email_verified")).lower() == "true",
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
        # #113: the profile's `email` field is whatever the user typed and is not
        # proof of anything, so it is ignored entirely. Only /user/emails carries
        # `verified`, and only a primary+verified address is accepted; anything
        # else comes back unverified and the callback refuses it.
        emails = httpx.get(
            "https://api.github.com/user/emails", headers=headers, timeout=15
        ).json()
        chosen = next(
            (e for e in emails if e.get("primary") and e.get("verified")), None
        )
        return OAuthIdentity(
            provider="github",
            subject=str(user["id"]),
            email=(chosen or {}).get("email") or "",
            display_name=user.get("name") or user.get("login"),
            email_verified=chosen is not None,
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
