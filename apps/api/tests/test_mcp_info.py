"""P17.2 — MCP connection metadata endpoint for the Integrations hub."""


def test_mcp_info_serves_launch_and_live_catalog(client):
    from app.mcp.registry import PROPOSE_TOOLS, READ_TOOLS

    r = client.get("/api/v1/integrations/mcp")
    assert r.status_code == 200
    data = r.json()
    assert data["server_name"] == "agentboard"
    assert data["command"] == "python"
    assert data["args"] == ["-m", "app.mcp.server"]
    assert data["capability_env"] == "AGENTBOARD_MCP_CAPABILITY"
    # Local mode (auth off by default in tests) → the real cwd is disclosed.
    assert data["cwd"] and data["cwd"].endswith("api")
    # Catalog mirrors the registry exactly — D37, never drifts from code.
    assert {t["name"] for t in data["read_tools"]} == set(READ_TOOLS)
    assert {t["name"] for t in data["propose_tools"]} == set(PROPOSE_TOOLS)
    assert all(t["description"] for t in data["read_tools"])


def test_mcp_info_hides_cwd_in_team_mode(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", True)
    r = client.get("/api/v1/integrations/mcp")
    assert r.status_code == 200
    assert r.json()["cwd"] is None
