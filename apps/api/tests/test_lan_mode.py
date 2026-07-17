"""Phase 11.0 — LAN team mode ceiling: host-allowlist widening + fail-closed auth.

LAN mode is OFF by default; when off, the app-wide Host allowlist is unchanged
(loopback + any 7C1 external hosts) and configured LAN hosts are inert. Turning
it on without auth is a startup error — the local control token is not an
identity (D25). With auth on, the configured LAN hosts pass the app-wide guard;
every other host still 403s, and loopback keeps working.
"""
from __future__ import annotations

import pytest

import app.main as app_main
from app.core.config import settings
from app.main import create_app

LAN_HOST = "192.168.1.50"


def _lan_on(monkeypatch, hosts: str = LAN_HOST) -> None:
    monkeypatch.setattr(settings, "lan_mode_enabled", True)
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "lan_allowed_hosts", hosts)


def test_lan_mode_disabled_by_default():
    assert settings.lan_mode_enabled is False
    assert settings.lan_allowed_hosts == ""


def test_lan_host_rejected_when_lan_mode_off(client, monkeypatch):
    # Configured hosts alone are inert — the ceiling flag gates them.
    monkeypatch.setattr(settings, "lan_allowed_hosts", LAN_HOST)
    res = client.get("/health", headers={"Host": LAN_HOST})
    assert res.status_code == 403


def test_lan_mode_without_auth_refuses_to_start(monkeypatch):
    monkeypatch.setattr(settings, "lan_mode_enabled", True)
    monkeypatch.setattr(settings, "auth_enabled", False)
    with pytest.raises(RuntimeError, match="AGENTBOARD_AUTH_ENABLED"):
        create_app()


def test_lan_host_accepted_when_enabled_with_auth(client, monkeypatch):
    _lan_on(monkeypatch)
    for host in (LAN_HOST, f"{LAN_HOST}:8000"):
        res = client.get("/health", headers={"Host": host})
        assert res.status_code == 200


def test_unlisted_host_still_rejected_in_lan_mode(client, monkeypatch):
    _lan_on(monkeypatch)
    res = client.get("/health", headers={"Host": "192.168.1.99"})
    assert res.status_code == 403


def test_loopback_still_accepted_in_lan_mode(client, monkeypatch):
    _lan_on(monkeypatch)
    res = client.get("/health", headers={"Host": "127.0.0.1"})
    assert res.status_code == 200


def test_lan_hosts_parse_whitespace_and_case(client, monkeypatch):
    _lan_on(monkeypatch, hosts=" 192.168.1.50 , Studio-PC.local ")
    for host in (LAN_HOST, "studio-pc.local:8000"):
        res = client.get("/health", headers={"Host": host})
        assert res.status_code == 200


def test_startup_warning_names_plain_http(monkeypatch):
    # Capture the logger call directly (not via caplog): immune to whatever
    # logging levels/handlers other tests in the suite have left behind.
    _lan_on(monkeypatch)
    messages: list[str] = []
    monkeypatch.setattr(
        app_main._log, "warning", lambda msg, *args, **kw: messages.append(msg % args)
    )
    create_app()
    assert any("UNENCRYPTED" in m for m in messages)
