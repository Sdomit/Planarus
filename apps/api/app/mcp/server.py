"""STDIO MCP transport adapter (Phase 7B).

The ONLY module that imports the MCP SDK. It maps the static registry to stdio
JSON-RPC: tools are listed/filtered by the launch-time capability, and each call
runs the pure handler in a worker thread against a fresh SQLModel session.

Invariants enforced here:
- STDIO only — no HTTP port, no shell.
- stdout is protocol-only; ALL logging goes to stderr.
- Structured errors only — never a traceback, DB URL, path, or SQL string.
- The server never runs migrations; if the schema is unavailable, calls return a
  structured ``unavailable`` error while tool metadata still lists fine.
"""
from __future__ import annotations

import json
import logging
import sys

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlmodel import Session

from app.db.session import engine
from app.mcp.capabilities import Capability, resolve_capability
from app.mcp.errors import (
    CODE_FORBIDDEN,
    CODE_INTERNAL,
    CODE_UNAVAILABLE,
    MCPToolError,
    error_payload,
)
from app.mcp.registry import ToolSpec, get_spec, visible_specs

logger = logging.getLogger("agentboard.mcp")

SERVER_NAME = "agentboard"


def _run_tool(spec: ToolSpec, capability: Capability, arguments: dict):
    """Validate args + run the handler in a fresh session. Returns (content, metadata)."""
    args = spec.validate_args(arguments)  # MCPToolError(invalid) on bad input
    try:
        with Session(engine) as session:
            result = spec.handler(session, capability, args)
    except (OperationalError, ProgrammingError):
        # Schema/DB not available — never leak the SQL/DB URL.
        raise MCPToolError(CODE_UNAVAILABLE, "Approvo data is unavailable")
    return (
        [types.TextContent(type="text", text=result.text)],
        result.metadata,
    )


def _error(code: str, message: str) -> "types.CallToolResult":
    """Structured error with the protocol-level isError flag set, so a client can
    detect a denial without string-parsing the body."""
    payload = error_payload(code, message)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structuredContent=payload,
        isError=True,
    )


def build_server(capability: Capability) -> Server:
    server: Server = Server(SERVER_NAME)

    @server.list_tools()
    async def _list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=spec.name,
                description=spec.description,
                inputSchema=spec.input_model.model_json_schema(),
            )
            for spec in visible_specs(capability)
        ]

    @server.call_tool(validate_input=False)
    async def _call_tool(name: str, arguments: dict):
        spec = get_spec(name, capability)
        if spec is None:
            return _error(CODE_FORBIDDEN, "tool not available")
        try:
            return await anyio.to_thread.run_sync(
                lambda: _run_tool(spec, capability, arguments or {})
            )
        except MCPToolError as exc:
            return _error(exc.code, exc.message)
        except Exception:  # noqa: BLE001 — never leak a traceback over the wire
            logger.exception("unexpected MCP tool error in %s", name)
            return _error(CODE_INTERNAL, "internal error")

    return server


async def _serve(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    # Logging to stderr ONLY — stdout is reserved for JSON-RPC protocol frames.
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    capability = resolve_capability()
    if not capability.valid:
        logger.warning(
            "starting with no valid capability (default-deny); set AGENTBOARD_MCP_CAPABILITY"
        )
    else:
        logger.info(
            "capability tier=%s projects=%d label=%s",
            capability.tier,
            len(capability.project_ids),
            capability.label,
        )
    server = build_server(capability)
    anyio.run(lambda: _serve(server))


if __name__ == "__main__":
    main()
