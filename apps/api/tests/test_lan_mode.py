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
    with pytest.raises(RuntimeError, match="PLANARUS_AUTH_ENABLED"):
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


# --- P11.3: the DB switch within the ceiling (process-local mirror) ------------
@pytest.fixture(autouse=True)
def _reset_lan_mirror():
    from app.services import settings_service

    settings_service._lan_switch_cache = None
    yield
    settings_service._lan_switch_cache = None


def test_lan_switch_off_pauses_acceptance_live(client, session, monkeypatch):
    from app.services import settings_service as svc

    _lan_on(monkeypatch)
    svc.set_setting(session, "lan_mode_active", False)
    session.commit()
    svc.refresh_lan_switch(session)
    assert client.get("/health", headers={"Host": LAN_HOST}).status_code == 403
    # loopback is never affected by the switch
    assert client.get("/health", headers={"Host": "127.0.0.1"}).status_code == 200
    # flipping back restores acceptance without a restart
    svc.set_setting(session, "lan_mode_active", True)
    session.commit()
    svc.refresh_lan_switch(session)
    assert client.get("/health", headers={"Host": LAN_HOST}).status_code == 200


def test_lan_switch_cannot_widen_past_ceiling(client, session, monkeypatch):
    from app.services import settings_service as svc

    # env ceiling OFF: a stored switch=true row must not open LAN hosts.
    monkeypatch.setattr(settings, "lan_allowed_hosts", LAN_HOST)
    svc.set_setting(session, "lan_mode_active", True)
    session.commit()
    svc.refresh_lan_switch(session)
    assert client.get("/health", headers={"Host": LAN_HOST}).status_code == 403


def test_put_settings_lan_switch_takes_effect_immediately(client, session, monkeypatch):
    from tests.external_util import local_hdr

    from app.services.auth_service import SESSION_COOKIE

    _lan_on(monkeypatch)
    # P16.1 (D35): with auth on, flipping switches requires a server admin —
    # the first account on the server bootstraps to admin (D29).
    monkeypatch.setattr(settings, "auth_dev_login_enabled", True)
    client.post("/api/v1/auth/dev-login", json={"email": "host@lan.local"})
    admin_cookie = {SESSION_COOKIE: client.cookies.get(SESSION_COOKIE)}
    client.cookies.clear()

    assert client.get("/health", headers={"Host": LAN_HOST}).status_code == 200
    res = client.put(
        "/api/v1/settings",
        headers=local_hdr(client),
        cookies=admin_cookie,
        json={"lan_mode_active": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["lan_mode_active"] is False
    assert client.get("/health", headers={"Host": LAN_HOST}).status_code == 403


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
