"""External calendar backends: OAuth token capture + Calendar API (Phase 15.12c/d).

A `CalendarBackend` bundles, per provider, the offline-OAuth flow (authorize →
exchange → refresh, keeping the refresh token the login OAuth discards) and the
event API (list/create/update/delete). Google and Microsoft are built in; a
provider is only *available* when its client id AND the encryption key are
configured — otherwise its routes 404 and nothing is reachable.

Network calls use httpx, imported lazily (the optional `[calendar-sync]` extra).
The real provider methods are `# pragma: no cover` — tests register a fake
backend and never touch the network, exactly like `oauth.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol
from urllib.parse import urlencode

from app.core import token_crypto
from app.core.config import settings

# The connect→callback flow state used to be a per-process HMAC blob defined
# here; it is now a server-side one-time transaction row shared with the login
# flow (#113) — see `app/services/oauth.py`.


@dataclass(frozen=True)
class CalendarTokens:
    access_token: str
    refresh_token: Optional[str]
    expiry: Optional[str]  # ISO datetime
    email: str
    scope: Optional[str] = None


@dataclass(frozen=True)
class RemoteEvent:
    external_uid: str
    etag: Optional[str]
    title: str
    start_at: str
    end_at: Optional[str]
    all_day: bool
    deleted: bool = False


@dataclass(frozen=True)
class PushEvent:
    """The local fields we send to a provider when creating/updating an event."""
    title: str
    start_at: str
    end_at: Optional[str]
    all_day: bool


class CalendarBackend(Protocol):
    name: str

    # OAuth (offline)
    def authorize_url(self, state: str, redirect_uri: str) -> str: ...
    def exchange_code(self, code: str, redirect_uri: str) -> CalendarTokens: ...
    def refresh(self, refresh_token: str) -> CalendarTokens: ...

    # Event API
    def list_events(
        self, access_token: str, sync_token: Optional[str]
    ) -> tuple[list[RemoteEvent], Optional[str]]: ...
    def create_event(self, access_token: str, ev: PushEvent) -> RemoteEvent: ...
    def delete_event(self, access_token: str, external_uid: str) -> None: ...


def _httpx():
    try:
        import httpx  # lazy: only for real sync
    except ImportError as exc:  # pragma: no cover - only without the extra
        raise RuntimeError(
            "Calendar sync requires httpx (install the [calendar-sync] extra)"
        ) from exc
    return httpx


def _expiry_from_seconds(expires_in: Optional[int]) -> Optional[str]:
    from datetime import timedelta

    from app.core.utils import now_utc  # ISO string
    if not expires_in:
        return None
    # now_utc() is an ISO string; parse, add, re-serialize.
    from datetime import datetime
    base = datetime.fromisoformat(now_utc())
    return (base + timedelta(seconds=int(expires_in))).isoformat()


# ── Google ────────────────────────────────────────────────────────────────
class GoogleCalendarBackend:
    name = "google"
    _SCOPE = "openid email https://www.googleapis.com/auth/calendar.events"
    _EVENTS = "https://www.googleapis.com/calendar/v3/calendars/primary/events"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._id, self._secret = client_id, client_secret

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        q = urlencode({
            "client_id": self._id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self._SCOPE,
            "access_type": "offline",  # ask for a refresh token
            "prompt": "consent",
            "state": state,
        })
        return f"https://accounts.google.com/o/oauth2/v2/auth?{q}"

    def exchange_code(self, code: str, redirect_uri: str) -> CalendarTokens:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": self._id, "client_secret": self._secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        }, timeout=15).json()
        info = httpx.get("https://openidconnect.googleapis.com/v1/userinfo",
                         headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=15).json()
        return CalendarTokens(
            access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
            expiry=_expiry_from_seconds(tok.get("expires_in")), email=info["email"], scope=self._SCOPE,
        )

    def refresh(self, refresh_token: str) -> CalendarTokens:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post("https://oauth2.googleapis.com/token", data={
            "refresh_token": refresh_token, "client_id": self._id,
            "client_secret": self._secret, "grant_type": "refresh_token",
        }, timeout=15).json()
        return CalendarTokens(
            access_token=tok["access_token"], refresh_token=refresh_token,
            expiry=_expiry_from_seconds(tok.get("expires_in")), email="", scope=self._SCOPE,
        )

    def _to_remote(self, it: dict) -> RemoteEvent:  # pragma: no cover - network
        start = it.get("start", {}); end = it.get("end", {})
        all_day = "date" in start
        return RemoteEvent(
            external_uid=it["id"], etag=it.get("etag"), title=it.get("summary", "(no title)"),
            start_at=start.get("date") or start.get("dateTime", ""),
            end_at=end.get("date") or end.get("dateTime"), all_day=all_day,
            deleted=it.get("status") == "cancelled",
        )

    def list_events(self, access_token, sync_token):  # pragma: no cover - network
        httpx = _httpx()
        params = {"syncToken": sync_token} if sync_token else {"maxResults": 250}
        r = httpx.get(self._EVENTS, headers={"Authorization": f"Bearer {access_token}"},
                      params=params, timeout=20).json()
        return [self._to_remote(it) for it in r.get("items", [])], r.get("nextSyncToken")

    def create_event(self, access_token, ev):  # pragma: no cover - network
        httpx = _httpx()
        body = {"summary": ev.title, **_google_times(ev)}
        r = httpx.post(self._EVENTS, headers={"Authorization": f"Bearer {access_token}"},
                       json=body, timeout=20).json()
        return self._to_remote(r)

    def delete_event(self, access_token, external_uid):  # pragma: no cover - network
        httpx = _httpx()
        httpx.delete(f"{self._EVENTS}/{external_uid}",
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=20)


def _google_times(ev: PushEvent) -> dict:  # pragma: no cover - network
    if ev.all_day:
        return {"start": {"date": ev.start_at[:10]}, "end": {"date": (ev.end_at or ev.start_at)[:10]}}
    return {"start": {"dateTime": ev.start_at}, "end": {"dateTime": ev.end_at or ev.start_at}}


# ── Microsoft (Graph) ──────────────────────────────────────────────────────
class MicrosoftCalendarBackend:
    name = "microsoft"
    _SCOPE = "offline_access openid email https://graph.microsoft.com/Calendars.ReadWrite"
    _EVENTS = "https://graph.microsoft.com/v1.0/me/events"

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._id, self._secret = client_id, client_secret

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        q = urlencode({
            "client_id": self._id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": self._SCOPE, "state": state, "response_mode": "query",
        })
        return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{q}"

    def exchange_code(self, code: str, redirect_uri: str) -> CalendarTokens:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token", data={
            "code": code, "client_id": self._id, "client_secret": self._secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "scope": self._SCOPE,
        }, timeout=15).json()
        me = httpx.get("https://graph.microsoft.com/v1.0/me",
                       headers={"Authorization": f"Bearer {tok['access_token']}"}, timeout=15).json()
        email = me.get("mail") or me.get("userPrincipalName", "")
        return CalendarTokens(
            access_token=tok["access_token"], refresh_token=tok.get("refresh_token"),
            expiry=_expiry_from_seconds(tok.get("expires_in")), email=email, scope=self._SCOPE,
        )

    def refresh(self, refresh_token: str) -> CalendarTokens:  # pragma: no cover - network
        httpx = _httpx()
        tok = httpx.post("https://login.microsoftonline.com/common/oauth2/v2.0/token", data={
            "refresh_token": refresh_token, "client_id": self._id, "client_secret": self._secret,
            "grant_type": "refresh_token", "scope": self._SCOPE,
        }, timeout=15).json()
        return CalendarTokens(
            access_token=tok["access_token"], refresh_token=tok.get("refresh_token", refresh_token),
            expiry=_expiry_from_seconds(tok.get("expires_in")), email="", scope=self._SCOPE,
        )

    def _to_remote(self, it: dict) -> RemoteEvent:  # pragma: no cover - network
        start = it.get("start", {}); end = it.get("end", {})
        all_day = bool(it.get("isAllDay"))
        return RemoteEvent(
            external_uid=it["id"], etag=it.get("@odata.etag"), title=it.get("subject", "(no title)"),
            start_at=start.get("dateTime", "")[:10] if all_day else start.get("dateTime", ""),
            end_at=(end.get("dateTime", "")[:10] if all_day else end.get("dateTime")),
            all_day=all_day, deleted=it.get("@removed") is not None,
        )

    def list_events(self, access_token, sync_token):  # pragma: no cover - network
        httpx = _httpx()
        url = sync_token or f"{self._EVENTS}?$top=250"
        r = httpx.get(url, headers={"Authorization": f"Bearer {access_token}"}, timeout=20).json()
        return [self._to_remote(it) for it in r.get("value", [])], r.get("@odata.deltaLink")

    def create_event(self, access_token, ev):  # pragma: no cover - network
        httpx = _httpx()
        body = {"subject": ev.title, "isAllDay": ev.all_day, **_ms_times(ev)}
        r = httpx.post(self._EVENTS, headers={"Authorization": f"Bearer {access_token}"},
                       json=body, timeout=20).json()
        return self._to_remote(r)

    def delete_event(self, access_token, external_uid):  # pragma: no cover - network
        httpx = _httpx()
        httpx.delete(f"{self._EVENTS}/{external_uid}",
                     headers={"Authorization": f"Bearer {access_token}"}, timeout=20)


def _ms_times(ev: PushEvent) -> dict:  # pragma: no cover - network
    s = ev.start_at if not ev.all_day else f"{ev.start_at[:10]}T00:00:00"
    e = (ev.end_at or ev.start_at) if not ev.all_day else f"{(ev.end_at or ev.start_at)[:10]}T00:00:00"
    return {"start": {"dateTime": s, "timeZone": "UTC"}, "end": {"dateTime": e, "timeZone": "UTC"}}


# ── Registry ────────────────────────────────────────────────────────────────
_test_backends: dict[str, CalendarBackend] = {}


def register_test_backend(name: str, backend: CalendarBackend) -> None:
    _test_backends[name] = backend


def reset_test_backends() -> None:
    _test_backends.clear()


def get_backend(name: str) -> Optional[CalendarBackend]:
    """A backend is usable only when encryption is on AND the provider is configured."""
    if name in _test_backends:
        return _test_backends[name]
    if not token_crypto.is_enabled():
        return None
    if name == "google" and settings.calendar_google_client_id:
        return GoogleCalendarBackend(settings.calendar_google_client_id, settings.calendar_google_client_secret)
    if name == "microsoft" and settings.calendar_microsoft_client_id:
        return MicrosoftCalendarBackend(settings.calendar_microsoft_client_id, settings.calendar_microsoft_client_secret)
    return None


def available_providers() -> list[str]:
    if _test_backends:
        return sorted(_test_backends)
    if not token_crypto.is_enabled():
        return []
    names = []
    if settings.calendar_google_client_id:
        names.append("google")
    if settings.calendar_microsoft_client_id:
        names.append("microsoft")
    return names
