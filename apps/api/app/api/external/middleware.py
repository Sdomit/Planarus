"""ASGI middleware for the Phase 7C1 external API boundary.

Two middlewares:

* ``ExternalApiGuard`` — the Host-header allowlist (DNS-rebinding defense;
  ``X-Forwarded-*`` is NEVER trusted) applies to EVERY http request: the local
  ``/api/v1`` surface is unauthenticated and ``/local-session`` hands out the
  control token, so a DNS-rebound page must fail the same check as the external
  surface. On ``/api/external/`` paths it additionally enforces, before routing:
    - disabled-by-default → generic 404 problem+json;
    - Cookie header rejection → 403 (external is Bearer-only);
    - 64 KiB body cap enforced by BOTH Content-Length and an actual streamed-byte
      count (handles missing/misleading length) → 413, without reading an
      unbounded body;
    - generates ``X-Request-Id`` and attaches it to every external response.

* ``PathScopedCORS`` — applies the normal local-UI CORS to everything EXCEPT the
  external surface. Starlette's CORS middleware is app-global; external paths must
  never emit a CORS header or answer a preflight, so they bypass it entirely.

This is DNS-rebinding + browser-isolation defense, not a network firewall: the
external API is loopback-bound and disabled by default.
"""
from __future__ import annotations

import json
import secrets
from typing import Optional

from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.external.problems import (
    PROBLEM_MEDIA_TYPE,
    REQUEST_ID_HEADER,
    problem_body,
)
from app.core.config import settings

EXTERNAL_PREFIX = "/api/external/"
MAX_BODY_BYTES = 64 * 1024

#: Ceiling for the local ``/api/v1`` surface (#117). Far above the external
#: 64 KiB cap because the local surface carries real documents: `content_json`
#: is capped at 2 MiB and `markdown_cache` at 2 MiB by `app.schemas.doc`, and a
#: canvas save sends both. This is the outer bound that stops an unbounded body
#: being buffered at all; the finer per-route limits live in the schemas, where
#: they can speak about fields rather than bytes:
#:
#:   * ``DocUpdate.content_json`` / ``markdown_cache`` — 2 MiB each
#:   * ``ProjectImport.data`` — see ``export_service.validate_import_payload``
#:     (entity counts, nesting depth, string sizes, total size)
LOCAL_MAX_BODY_BYTES = 8 * 1024 * 1024
LOCAL_PREFIX = "/api/v1"
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]")
_BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _gen_request_id() -> str:
    return "req_" + secrets.token_hex(12)


def _add_csv_hosts(hosts: set[str], csv: str) -> None:
    for h in (csv or "").split(","):
        cleaned = h.strip().lower()
        if cleaned:
            hosts.add(cleaned)


def _allowed_hosts() -> set[str]:
    from app.services.settings_service import lan_switch_cached

    hosts = {h.lower() for h in DEFAULT_ALLOWED_HOSTS}
    _add_csv_hosts(hosts, settings.external_api_allowed_hosts)
    # Phase 11.0: LAN team mode widens the app-wide allowlist to the configured
    # LAN hosts. Triply gated: the env ceiling here, the P11.3 DB switch within
    # it (a process-local mirror — pause LAN acceptance from the Settings UI
    # without a restart, no per-request DB read in middleware), and
    # create_app()'s refusal to start LAN mode without auth enabled (D25).
    if settings.lan_mode_enabled and lan_switch_cached():
        _add_csv_hosts(hosts, settings.lan_allowed_hosts)
    return hosts


def _host_ok(host_header: Optional[bytes]) -> bool:
    """Validate the Host header against the loopback (or configured) allowlist.

    Parses an optional port and IPv6 bracket form. Never consults forwarded headers.
    """
    if not host_header:
        return False
    host = host_header.decode("latin-1").strip().lower()
    if not host:
        return False
    if host.startswith("["):  # IPv6 literal, e.g. [::1] or [::1]:8000
        end = host.find("]")
        if end == -1:
            return False
        hostname = host[: end + 1]
    else:
        hostname = host.split(":", 1)[0]
    return hostname in _allowed_hosts()


async def _send_problem(
    send: Send,
    status: int,
    slug: str,
    title: str,
    detail: str,
    request_id: str,
    *,
    retry_after: Optional[int] = None,
) -> None:
    body = json.dumps(problem_body(status, slug, title, detail, request_id)).encode("utf-8")
    headers = [
        (b"content-type", PROBLEM_MEDIA_TYPE.encode("latin-1")),
        (b"content-length", str(len(body)).encode("latin-1")),
        (REQUEST_ID_HEADER.lower().encode("latin-1"), request_id.encode("latin-1")),
    ]
    if retry_after is not None:
        headers.append((b"retry-after", str(int(retry_after)).encode("latin-1")))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _send_too_large(send: Send, request_id: str) -> None:
    """413 for the local surface, in FastAPI's ``{"detail": ...}`` shape.

    Deliberately not ``problem+json``: that media type is the external API's
    contract, and the web client parses ``detail`` like every other /api/v1
    error. The request id still travels, in the same header.
    """
    body = json.dumps(
        {
            "detail": (
                f"request body exceeds the "
                f"{LOCAL_MAX_BODY_BYTES // (1024 * 1024)} MiB limit"
            ),
            "request_id": request_id,
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("latin-1")),
                (REQUEST_ID_HEADER.lower().encode("latin-1"), request_id.encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _read_capped_body(receive: Receive, limit: int) -> tuple[bytes, bool]:
    """Read the request body, capping at ``limit`` bytes. Returns (body, exceeded)."""
    chunks: list[bytes] = []
    total = 0
    more = True
    while more:
        message = await receive()
        if message["type"] == "http.disconnect":
            break
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > limit:
            return b"", True
        chunks.append(chunk)
        more = message.get("more_body", False)
    return b"".join(chunks), False


def _replay_receive(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def _send_with_request_id(send: Send, request_id: str) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = list(message.get("headers") or [])
            if not any(k.lower() == b"x-request-id" for k, _ in headers):
                headers.append((b"x-request-id", request_id.encode("latin-1")))
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


class ExternalApiGuard:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])

        if not scope.get("path", "").startswith(EXTERNAL_PREFIX):
            # Local surface (/api/v1, /health, /docs): same strict Host check,
            # plus the #117 body ceiling. CORS, auth and error shapes are
            # otherwise untouched.
            if not _host_ok(headers.get(b"host")):
                await _send_problem(send, 403, "forbidden_host", "Forbidden",
                                    "host not allowed", _gen_request_id())
                return
            if scope.get("method") in _BODY_METHODS and scope.get("path", "").startswith(
                LOCAL_PREFIX
            ):
                request_id = _gen_request_id()
                # Declared length first: an honest oversized upload is refused
                # before a single byte is read.
                content_length = headers.get(b"content-length")
                if content_length is not None:
                    try:
                        declared = int(content_length)
                    except ValueError:
                        declared = -1
                    if declared > LOCAL_MAX_BODY_BYTES:
                        await _send_too_large(send, request_id)
                        return
                # Then the actual stream, because Content-Length can be absent
                # (chunked) or simply lie.
                body, exceeded = await _read_capped_body(receive, LOCAL_MAX_BODY_BYTES)
                if exceeded:
                    await _send_too_large(send, request_id)
                    return
                await self.app(
                    scope, _replay_receive(body), _send_with_request_id(send, request_id)
                )
                return
            await self.app(scope, receive, send)
            return

        request_id = _gen_request_id()
        scope.setdefault("state", {})["request_id"] = request_id

        # Disabled by default → generic 404 (indistinguishable from "no such route").
        if not settings.external_api_enabled:
            await _send_problem(send, 404, "not_found", "Not Found",
                                "the requested resource was not found", request_id)
            return

        if not _host_ok(headers.get(b"host")):
            await _send_problem(send, 403, "forbidden_host", "Forbidden",
                                "host not allowed", request_id)
            return

        if b"cookie" in headers:
            await _send_problem(send, 403, "cookie_not_allowed", "Forbidden",
                                "cookies are not accepted on the external API", request_id)
            return

        method = scope.get("method", "GET").upper()
        replay: Optional[bytes] = None
        if method in _BODY_METHODS:
            content_length = headers.get(b"content-length")
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError:
                    await _send_problem(send, 400, "malformed_request", "Bad Request",
                                        "invalid Content-Length", request_id)
                    return
                if declared > MAX_BODY_BYTES:
                    await _send_problem(send, 413, "payload_too_large", "Payload Too Large",
                                        "request body exceeds the 64 KiB limit", request_id)
                    return
            body, exceeded = await _read_capped_body(receive, MAX_BODY_BYTES)
            if exceeded:
                await _send_problem(send, 413, "payload_too_large", "Payload Too Large",
                                    "request body exceeds the 64 KiB limit", request_id)
                return
            replay = body

        downstream_receive = _replay_receive(replay) if replay is not None else receive
        await self.app(scope, downstream_receive, _send_with_request_id(send, request_id))


class PathScopedCORS:
    """Apply CORS to everything EXCEPT ``/api/external/`` (which must get no CORS)."""

    def __init__(self, app: ASGIApp, **cors_options) -> None:
        self.app = app
        self.cors = CORSMiddleware(app, **cors_options)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path", "").startswith(EXTERNAL_PREFIX):
            await self.app(scope, receive, send)
        else:
            await self.cors(scope, receive, send)
