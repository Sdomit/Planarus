"""App-wide Host allowlist (DNS-rebinding defense for the local surface).

The unauthenticated /api/v1 surface and /health now get the same strict Host
check as /api/external/: loopback (or explicitly configured) hostnames only,
with forwarded headers never consulted. The conftest TestClient targets
``http://localhost`` so ordinary tests pass the guard.
"""
from __future__ import annotations

import pytest

WORKSPACES = "/api/v1/workspaces"


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "localhost", "localhost:5173", "127.0.0.1:8000", "[::1]"]
)
def test_v1_loopback_hosts_accepted(client, host):
    res = client.get(WORKSPACES, headers={"Host": host})
    assert res.status_code == 200


@pytest.mark.parametrize("host", ["evil.example", "testserver", "169.254.0.1", ""])
def test_v1_foreign_or_missing_host_rejected(client, host):
    res = client.get(WORKSPACES, headers={"Host": host})
    assert res.status_code == 403


def test_v1_forwarded_headers_not_trusted(client):
    res = client.get(
        WORKSPACES,
        headers={
            "Host": "evil.example",
            "X-Forwarded-Host": "127.0.0.1",
            "X-Forwarded-For": "127.0.0.1",
        },
    )
    assert res.status_code == 403


def test_local_session_foreign_host_rejected(client):
    res = client.get("/api/v1/local-session", headers={"Host": "evil.example"})
    assert res.status_code == 403


def test_health_foreign_host_rejected(client):
    res = client.get("/health", headers={"Host": "evil.example"})
    assert res.status_code == 403


def test_configured_public_host_accepted_locally(client, monkeypatch):
    # The tunnel fronting flow (7C2b) pins the public hostname; once configured
    # it must pass on local paths too (cloudflared health checks hit /health).
    from app.core.config import settings

    monkeypatch.setattr(settings, "external_api_allowed_hosts", "agentboard.example.com")
    res = client.get("/health", headers={"Host": "agentboard.example.com"})
    assert res.status_code == 200
