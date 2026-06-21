"""Launch-time capability scope guard for the MCP server (Phase 7B).

Resolved ONCE at process start from the ``AGENTBOARD_MCP_CAPABILITY`` env var —
never from a tool argument. Two tiers only: ``read`` and ``propose``. There is no
approve/apply tier. Any missing, malformed, oversized, or empty capability is
**default-deny**.

Honest scope note: this is a *local scope guard*, not authentication against a
hostile local process. A process the user launches already runs with the user's
privileges and could read the SQLite file directly; defending against that is out
of Phase 7B's trust model. The guard limits what THIS server exposes to the model
it serves, and which projects are reachable.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping, Optional

ENV_VAR = "AGENTBOARD_MCP_CAPABILITY"
MAX_PROJECT_IDS = 50
MAX_LABEL_LEN = 64
MAX_RAW_LEN = 8192
_TIERS = ("read", "propose")


@dataclass(frozen=True)
class Capability:
    tier: str
    workspace_id: str
    project_ids: frozenset[str]
    label: str
    valid: bool = True

    @property
    def actor_ref(self) -> str:
        return f"mcp:{self.label}"

    def allows_project(self, project_id: str) -> bool:
        return self.valid and project_id in self.project_ids


# The default-deny capability: valid=False, no projects, read tier (lowest power).
DENY = Capability(
    tier="read", workspace_id="", project_ids=frozenset(), label="denied", valid=False
)


def _safe_label(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        return "client"
    cleaned = "".join(c for c in raw if c.isalnum() or c in "-_. ").strip()
    return cleaned[:MAX_LABEL_LEN] or "client"


def parse_capability(raw: Optional[str]) -> Capability:
    if not raw or not isinstance(raw, str) or len(raw) > MAX_RAW_LEN:
        return DENY
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return DENY
    if not isinstance(data, dict):
        return DENY

    tier = data.get("tier")
    if tier not in _TIERS:
        return DENY

    workspace_id = data.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id:
        return DENY

    pids = data.get("project_ids")
    if not isinstance(pids, list) or not pids or len(pids) > MAX_PROJECT_IDS:
        return DENY
    if not all(isinstance(p, str) and p for p in pids):
        return DENY

    return Capability(
        tier=tier,
        workspace_id=workspace_id,
        project_ids=frozenset(pids),
        label=_safe_label(data.get("label")),
        valid=True,
    )


def resolve_capability(env: Optional[Mapping[str, str]] = None) -> Capability:
    """Resolve the capability from the environment (or an injected mapping for tests)."""
    source = env if env is not None else os.environ
    return parse_capability(source.get(ENV_VAR))
