"""P17.4 — remote MCP over Streamable HTTP (D39).

Mounts the SAME static tool registry over HTTP at ``/api/external/v1/mcp``,
authenticated by the SAME ``agbk_`` keys and scope-gated exactly like the REST
API. The STDIO server (``app/mcp/server.py``) is unchanged: this module builds
its own server whose handlers read the per-request capability from a contextvar,
driven through one stateless ``StreamableHTTPSessionManager``.

Security posture (all inherited or reused — nothing new invented):
  * Ceiling: mounted under ``/api/external/``, so ``ExternalApiGuard`` already
    enforces disabled-by-default (env 404), the Host allowlist, cookie rejection,
    and the 64 KiB body cap before this code runs.
  * Auth: reuses ``app.api.external.auth._authenticate`` — the DB switch check,
    Argon2id verify, generic 401, and key→capability scoping are identical to the
    REST surface. No key ⇒ no tools (default-deny).
  * Scope: a read key sees the 10 read tools; a propose key additionally sees the 4
    propose tools; a read key that calls a propose tool is denied by ``get_spec``.
  * Never widens power (D40): read + create-pending-proposal only; no approve/apply.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Optional

import anyio
from fastapi import FastAPI
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import Receive, Scope, Send

from app.api.external.auth import _authenticate, _rate_and_concurrency
from app.api.external.middleware import _send_problem
from app.api.external.problems import ExternalProblem
from app.core.rate_limit import limiter
from app.db.session import get_session
from app.mcp.capabilities import Capability
from app.mcp.errors import CODE_FORBIDDEN, CODE_INTERNAL, MCPToolError
from app.mcp.registry import get_spec, visible_specs
from app.mcp.server import SERVER_NAME, _error, _run_tool, instructions_for

MOUNT_PATH = "/api/external/v1/mcp"

# Per-request capability, set by the auth wrapper and read by the tool handlers.
_capability: ContextVar[Capability] = ContextVar("_mcp_http_capability")


def _build_http_server() -> Server:
    """A server whose visible/callable tools follow the per-request capability."""
    # No capability at construction time, so the orientation describes both tiers.
    server: Server = Server(SERVER_NAME, instructions=instructions_for())

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        cap = _capability.get()
        return [
            types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_model.model_json_schema(),
                outputSchema=spec.output_schema,
            )
            for spec in visible_specs(cap)
        ]

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict):
        cap = _capability.get()
        spec = get_spec(name, cap)  # None ⇒ out of scope / not visible to this key
        if spec is None:
            return _error(CODE_FORBIDDEN, "tool not available")
        try:
            return await anyio.to_thread.run_sync(
                lambda: _run_tool(spec, cap, arguments or {})
            )
        except MCPToolError as exc:
            return _error(exc.code, exc.message)
        except Exception:  # noqa: BLE001 — never leak a traceback over the wire
            return _error(CODE_INTERNAL, "internal error")

    return server


def _new_manager() -> StreamableHTTPSessionManager:
    """A fresh stateless manager. A manager's run() may be entered only ONCE per
    instance, so the lifespan makes a new one each time the app starts (and tests
    make their own). ExternalApiGuard owns the Host allowlist for /api/external/*,
    so the SDK's DNS-rebind check is disabled rather than diverging from it."""
    return StreamableHTTPSessionManager(
        app=_build_http_server(),
        stateless=True,
        json_response=True,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


_manager = _new_manager()


@asynccontextmanager
async def mcp_lifespan(_app: FastAPI):
    """Run a fresh streamable-HTTP session manager for the app's lifetime."""
    global _manager
    _manager = _new_manager()
    async with _manager.run():
        yield


def _bearer(scope: Scope) -> Optional[str]:
    value = dict(scope.get("headers") or []).get(b"authorization")
    return value.decode("latin-1") if value else None


def make_mcp_mount(app: FastAPI):
    """ASGI app for the MCP mount. Closes over ``app`` so it honours the test
    ``get_session`` override; in production it opens a real session."""

    async def mcp_mount(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        request_id = (scope.get("state") or {}).get("request_id", "req")
        override = app.dependency_overrides.get(get_session)
        gen = (override or get_session)()
        session = next(gen)
        try:
            try:
                client, cap = _authenticate(None, session, _bearer(scope))
                # Per-key rate + concurrency gate, matching the REST surface
                # (require_external_read): each MCP POST is gated as a read and holds
                # a concurrency slot for the request, released below. Propose tools
                # still route through human approval regardless.
                _rate_and_concurrency(client, propose=False)
            except ExternalProblem as problem:
                await _send_problem(
                    send, problem.status, problem.slug, problem.title,
                    problem.detail, request_id, retry_after=problem.retry_after,
                )
                return
            token = _capability.set(cap)
            try:
                await _manager.handle_request(scope, receive, send)
            finally:
                _capability.reset(token)
                try:
                    limiter.release(client.key_id)
                except Exception:  # noqa: BLE001 — release must never raise into the response
                    pass
        finally:
            gen.close()

    return mcp_mount
