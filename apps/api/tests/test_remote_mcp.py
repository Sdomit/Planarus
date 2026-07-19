"""P17.4 — remote MCP over Streamable HTTP (D39).

Drives the real MCP client against the mounted app over an in-process ASGI
transport, proving: agbk_ auth is required, tools are scope-gated exactly like
the REST API (read key → 9 read tools and no propose reach; propose key → 13),
the surface is disabled-by-default, and a scoped read returns real data.

A session manager's run() is single-use per instance, so each test uses its own
fresh manager (and points the module global at it, since the mount reads it).
"""
import anyio
import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.main import app
from app.mcp import http_transport
from app.mcp.http_transport import MOUNT_PATH
from tests.external_util import auth, issue_key, seed

# Trailing slash: the mounted ASGI app's canonical path (the bare form 307s to it).
URL = f"http://127.0.0.1{MOUNT_PATH}/"


def _asgi_factory(headers=None, timeout=None, auth=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1",
        headers=headers,
        timeout=timeout or httpx.Timeout(30),
        auth=auth,
        follow_redirects=True,
    )


def _fresh_manager(monkeypatch):
    mgr = http_transport._new_manager()
    monkeypatch.setattr(http_transport, "_manager", mgr)
    return mgr


async def _run(mgr, headers, *, probe=None):
    """Initialize, list tools, optionally call one. → (names, probe_is_error, text)."""
    async with mgr.run():
        async with streamablehttp_client(
            URL, headers=headers, httpx_client_factory=_asgi_factory
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = [t.name for t in (await session.list_tools()).tools]
                if probe is None:
                    return names, None, None
                try:
                    call = await session.call_tool(probe, {"project_id": "x", "title": "t"})
                    text = call.content[0].text if call.content else ""
                    return names, bool(getattr(call, "isError", False)), text
                except Exception:
                    return names, True, ""


async def _read_projects(mgr, headers):
    async with mgr.run():
        async with streamablehttp_client(
            URL, headers=headers, httpx_client_factory=_asgi_factory
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                call = await session.call_tool("list_projects", {})
                return call.content[0].text if call.content else ""


def test_remote_mcp_disabled_by_default(client, monkeypatch):
    # No `external_api` fixture → ExternalApiGuard 404s the surface before auth.
    mgr = _fresh_manager(monkeypatch)
    ws, proj = seed(client, "rmcpoff")
    _meta, key = issue_key(client, ws, [proj])
    with pytest.raises(Exception):
        anyio.run(lambda: _run(mgr, auth(key)))


def test_remote_mcp_requires_a_valid_key(client, external_api, monkeypatch):
    mgr = _fresh_manager(monkeypatch)
    with pytest.raises(Exception):
        anyio.run(lambda: _run(mgr, {"Host": "127.0.0.1"}))  # no Authorization


def test_remote_mcp_read_key_sees_read_tools_only(client, external_api, monkeypatch):
    mgr = _fresh_manager(monkeypatch)
    ws, proj = seed(client, "rmcpread")
    _meta, key = issue_key(client, ws, [proj], can_read=True, can_propose=False)
    names, probe_err, _text = anyio.run(lambda: _run(mgr, auth(key), probe="create_task_proposal"))
    assert len(names) == 9
    assert "list_projects" in names
    assert "create_task_proposal" not in names
    # A read key cannot reach a propose tool even by naming it directly.
    assert probe_err is True


def test_remote_mcp_propose_key_sees_all_tools(client, external_api, monkeypatch):
    mgr = _fresh_manager(monkeypatch)
    ws, proj = seed(client, "rmcpprop")
    _meta, key = issue_key(client, ws, [proj], can_read=True, can_propose=True)
    names, _e, _t = anyio.run(lambda: _run(mgr, auth(key)))
    assert len(names) == 13
    assert {"create_task_proposal", "update_canvas_proposal"} <= set(names)


def test_remote_mcp_scoped_read_returns_data(client, external_api, engine, monkeypatch):
    # Point tool execution at the in-memory test DB (StaticPool shares the
    # connection, so the seeded project is visible to a fresh Session).
    monkeypatch.setattr("app.mcp.server.engine", engine)
    mgr = _fresh_manager(monkeypatch)
    ws, proj = seed(client, "rmcpdata")
    _meta, key = issue_key(client, ws, [proj], can_read=True)
    text = anyio.run(lambda: _read_projects(mgr, auth(key)))
    # The project id is a high-entropy string → redacted in reference-only output;
    # assert on the (non-redacted) title, which proves the scoped read returned it.
    assert "title: P" in text
