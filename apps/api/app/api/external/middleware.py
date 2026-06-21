"""ASGI middleware for the Phase 7C1 external API boundary.

Two middlewares, both scoped to ``/api/external/``:

* ``ExternalApiGuard`` — runs before routing on external paths only:
    - disabled-by-default → generic 404 problem+json;
    - Host-header allowlist (DNS-rebinding defense; ``X-Forwarded-*`` is NEVER
      trusted) → 403;
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
DEFAULT_ALLOWED_HOSTS = ("localhost", "127.0.0.1", "[::1]")
_BODY_METHODS = ("POST", "PUT", "PATCH", "DELETE")


def _gen_request_id() -> str:
    return "req_" + secrets.token_hex(12)


def _allowed_hosts() -> set[str]:
    hosts = {h.lower() for h in DEFAULT_ALLOWED_HOSTS}
    for h in (settings.external_api_allowed_hosts or "").split(","):
        cleaned = h.strip().lower()
        if cleaned:
            hosts.add(cleaned)
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
        if scope["type"] != "http" or not scope.get("path", "").startswith(EXTERNAL_PREFIX):
            await self.app(scope, receive, send)
            return

        request_id = _gen_request_id()
        scope.setdefault("state", {})["request_id"] = request_id

        # Disabled by default → generic 404 (indistinguishable from "no such route").
        if not settings.external_api_enabled:
            await _send_problem(send, 404, "not_found", "Not Found",
                                "the requested resource was not found", request_id)
            return

        headers = dict(scope.get("headers") or [])

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
