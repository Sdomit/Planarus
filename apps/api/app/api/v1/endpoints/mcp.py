"""P17.2 — read-only MCP connection metadata for the Integrations hub.

Surface-only. Serves the STDIO launch command, this install's working directory
(local mode only — the settings surface's "never disclose a raw host/path" rule
applies in team mode), the capability env-var name, and the static tool catalog
straight from ``app/mcp/registry.py`` so the Settings → Integrations MCP card can
render paste-ready client config plus a tool list that can never drift from code
(D37). No secrets, no capability value, no mutation. Ungated like ``/info``.

Does NOT import ``app.mcp.server`` (the only MCP-SDK importer) — the server name
is a stable constant and the registry/capabilities modules are SDK-free.
"""
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings as env
from app.mcp.capabilities import ENV_VAR
from app.mcp.registry import PROPOSE_TOOLS, READ_TOOLS

router = APIRouter()

SERVER_NAME = "agentboard"  # mirrors app.mcp.server.SERVER_NAME (kept SDK-free)

# apps/api — the cwd from which ``python -m app.mcp.server`` can import ``app``.
# This file is apps/api/app/api/v1/endpoints/mcp.py → parents[4] == apps/api.
_APP_ROOT = str(Path(__file__).resolve().parents[4])


def _catalog(specs: dict) -> list[dict]:
    return [{"name": s.name, "description": s.description} for s in specs.values()]


@router.get("/integrations/mcp")
def get_mcp_info() -> dict:
    return {
        "server_name": SERVER_NAME,
        "command": "python",
        "args": ["-m", "app.mcp.server"],
        # Real path only in local single-user mode; team mode follows the
        # settings surface's no-raw-path rule.
        "cwd": None if env.auth_enabled else _APP_ROOT,
        "capability_env": ENV_VAR,
        "read_tools": _catalog(READ_TOOLS),
        "propose_tools": _catalog(PROPOSE_TOOLS),
    }
