"""Shared helpers for Phase 7B MCP tests (not collected as tests)."""
from __future__ import annotations

from app.mcp.capabilities import Capability
from fastapi.testclient import TestClient

# THE expected tool catalogue. Every tier/count/name assertion across the MCP
# tests derives from these two sets — nothing hard-codes a tool count.
#
# That indirection is not ceremony. Four test files used to carry the literal
# "9 read + 4 propose = 13", so any branch adding a tool had to edit the same
# four magic numbers, and two branches adding *different* tools would either
# conflict on every one or (worse) merge cleanly to a number that was wrong for
# the union. Adding a tool is now a one-line edit here, and two branches adding
# to different tiers touch different lines.
#
# Set equality, not length, is what the tests assert: it is strictly stronger
# and it names the offending tool when it fails.
EXPECTED_READ_TOOLS: frozenset[str] = frozenset(
    {
        "list_projects",
        "get_project_summary",
        "get_active_work",
        "list_tasks",
        "list_decisions",
        "list_risks",
        "list_docs",
        "get_doc_excerpt",
        "get_item",
        "get_approval_status",
    }
)

EXPECTED_PROPOSE_TOOLS: frozenset[str] = frozenset(
    {
        "create_task_proposal",
        "update_task_proposal",
        "create_decision_proposal",
        "update_canvas_proposal",
        "create_connection_proposal",
    }
)

EXPECTED_ALL_TOOLS: frozenset[str] = EXPECTED_READ_TOOLS | EXPECTED_PROPOSE_TOOLS


def seed(client: TestClient, suffix: str) -> tuple[str, str]:
    """Create a workspace + project via the API; return (workspace_id, project_id)."""
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return ws["id"], proj["id"]


def read_cap(workspace_id: str, *project_ids: str) -> Capability:
    return Capability(
        tier="read",
        workspace_id=workspace_id,
        project_ids=frozenset(project_ids),
        label="test",
    )


def propose_cap(workspace_id: str, *project_ids: str) -> Capability:
    return Capability(
        tier="propose",
        workspace_id=workspace_id,
        project_ids=frozenset(project_ids),
        label="test",
    )
