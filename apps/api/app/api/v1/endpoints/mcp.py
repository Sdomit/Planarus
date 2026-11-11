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
import sys
from pathlib import Path

from fastapi import APIRouter

from app.core.config import settings as env
from app.mcp.capabilities import ENV_VAR
from app.mcp.registry import PROPOSE_TOOLS, READ_TOOLS

router = APIRouter()

SERVER_NAME = "planarus"  # mirrors app.mcp.server.SERVER_NAME (kept SDK-free)

# apps/api — the cwd from which ``python -m app.mcp.server`` can import ``app``.
# This file is apps/api/app/api/v1/endpoints/mcp.py → parents[4] == apps/api.
_APP_ROOT = str(Path(__file__).resolve().parents[4])


def _local_sqlite_url() -> str | None:
    """Give local MCP clients this instance's SQLite file, even when launched
    from a different cwd. Never return a network DB URL or a team-mode path."""
    if env.auth_enabled or not env.database_url.startswith("sqlite:///"):
        return None
    raw_path = env.database_url.removeprefix("sqlite:///")
    if not raw_path or raw_path == ":memory:" or "?" in raw_path:
        return None
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = Path(_APP_ROOT) / db_path
    return f"sqlite:///{db_path.resolve().as_posix()}"


def _catalog(specs: dict) -> list[dict]:
    return [{"name": s.name, "description": s.description} for s in specs.values()]


@router.get("/integrations/mcp")
def get_mcp_info() -> dict:
    return {
        "server_name": SERVER_NAME,
        # Use the interpreter already running the local API, which has the MCP
        # package installed. Team mode must not disclose a host path.
        "command": "python" if env.auth_enabled else sys.executable,
        "args": ["-m", "app.mcp.server"],
        # Real path only in local single-user mode; team mode follows the
        # settings surface's no-raw-path rule.
        "cwd": None if env.auth_enabled else _APP_ROOT,
        "database_url": _local_sqlite_url(),
        "capability_env": ENV_VAR,
        "read_tools": _catalog(READ_TOOLS),
        "propose_tools": _catalog(PROPOSE_TOOLS),
    }
