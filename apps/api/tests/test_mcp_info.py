"""P17.2 — MCP connection metadata endpoint for the Integrations hub."""


def test_mcp_info_serves_launch_and_live_catalog(client):
    from app.mcp.registry import PROPOSE_TOOLS, READ_TOOLS

    r = client.get("/api/v1/integrations/mcp")
    assert r.status_code == 200
    data = r.json()
    assert data["server_name"] == "planarus"
    import sys

    assert data["command"] == sys.executable
    assert data["args"] == ["-m", "app.mcp.server"]
    assert data["capability_env"] == "PLANARUS_MCP_CAPABILITY"
    # Local mode (auth off by default in tests) → the real cwd is disclosed.
    assert data["cwd"] and data["cwd"].endswith("api")
    assert data["database_url"].startswith("sqlite:///")
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
    assert r.json()["command"] == "python"
    assert r.json()["database_url"] is None


def test_mcp_info_uses_absolute_local_sqlite_path(monkeypatch):
    from app.api.v1.endpoints.mcp import get_mcp_info
    from app.core.config import settings

    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "database_url", "sqlite:///./planarus.db")
    data = get_mcp_info()
    assert data["database_url"].startswith("sqlite:///")
    assert data["database_url"].endswith("/apps/api/planarus.db")

    monkeypatch.setattr(settings, "database_url", "postgresql://user:password@localhost/db")
    assert get_mcp_info()["database_url"] is None
