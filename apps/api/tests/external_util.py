"""Shared helpers for Phase 7C1 external-API tests (not collected as tests)."""
from __future__ import annotations

from fastapi.testclient import TestClient

# The external host guard only accepts loopback hosts; TestClient defaults to
# Host: testserver (a deliberately *foreign* host), so external requests must set
# a loopback Host explicitly.
LOOPBACK = {"Host": "127.0.0.1"}


def local_hdr(client: TestClient) -> dict:
    token = client.get("/api/v1/local-session").json()["token"]
    return {"X-AgentBoard-Local-Token": token}


def seed(client: TestClient, suffix: str) -> tuple[str, str]:
    """Create a workspace + project; return (workspace_id, project_id)."""
    ws = client.post("/api/v1/workspaces", json={"name": "WS", "slug": f"ws-{suffix}"}).json()
    proj = client.post(
        "/api/v1/projects",
        json={"workspace_id": ws["id"], "title": "P", "slug": f"p-{suffix}"},
    ).json()
    return ws["id"], proj["id"]


def create_api_client(
    client: TestClient,
    workspace_id: str,
    project_ids,
    *,
    can_read: bool = True,
    can_propose: bool = False,
    label: str = "test-key",
    expires_in_days: int | None = None,
):
    body = {
        "label": label,
        "workspace_id": workspace_id,
        "project_ids": list(project_ids),
        "can_read": can_read,
        "can_propose": can_propose,
    }
    if expires_in_days is not None:
        body["expires_in_days"] = expires_in_days
    return client.post("/api/v1/api-clients", headers=local_hdr(client), json=body)


def issue_key(client: TestClient, workspace_id: str, project_ids, **kwargs) -> tuple[dict, str]:
    """Create a client and return (client_metadata, raw_key)."""
    res = create_api_client(client, workspace_id, project_ids, **kwargs)
    assert res.status_code == 201, res.text
    data = res.json()
    return data["client"], data["api_key"]


def auth(raw_key: str, host: str = "127.0.0.1") -> dict:
    return {"Authorization": f"Bearer {raw_key}", "Host": host}
