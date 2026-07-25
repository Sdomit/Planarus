"""Shared helpers for Phase 7B MCP tests (not collected as tests)."""
from __future__ import annotations

from app.mcp.capabilities import Capability
from fastapi.testclient import TestClient


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
