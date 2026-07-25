"""Phase 9B — runtime settings & connection manager.

Covers the switch/ceiling/secret tiers: switches flip live, the env ceiling wins,
GET never discloses a secret or raw host, and the external-API DB switch turns the
external surface off (indistinguishably from disabled) while the ceiling permits it.
"""
import pytest
from app.models.setting import Setting
from app.schemas.settings import SettingsUpdate
from app.services import settings_service as svc

from tests.external_util import auth, issue_key, local_hdr, seed


@pytest.fixture(autouse=True)
def _reset_lan_mirror():
    """write_settings refreshes the P11.3 process-local LAN mirror — reset it so
    settings writes here never leak switch state into other modules."""
    svc._lan_switch_cache = None
    yield
    svc._lan_switch_cache = None

# --- accessor unit tests ------------------------------------------------------


def test_get_setting_default_and_roundtrip(session):
    assert svc.get_setting(session, "email_from", "d@x") == "d@x"  # unset → default
    svc.set_setting(session, "email_from", "team@example.com")
    session.commit()
    assert svc.get_setting(session, "email_from", "d@x") == "team@example.com"


def test_get_setting_corrupt_value_falls_back(session):
    session.add(Setting(key="email_enabled", value="{not json", updated_at="t"))
    session.commit()
    assert svc.get_setting(session, "email_enabled", False) is False


def test_write_settings_only_touches_provided_keys(session):
    svc.write_settings(session, SettingsUpdate(email_enabled=True))
    read = svc.read_settings(session)
    assert read.email_enabled is True
    # email_from was not provided → still the env default, no row written.
    assert session.get(Setting, "email_from") is None


# --- endpoint tests -----------------------------------------------------------


def test_get_settings_shape_and_no_secret_leak(client):
    res = client.get("/api/v1/settings")
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) == {
        "email_enabled", "email_from", "external_api_active",
        "external_api_permitted_by_env", "external_api_hosts_configured",
        "email_smtp_loopback",
        # P11.3 LAN section — switch + boolean-only ceiling status
        "lan_mode_active", "lan_permitted_by_env", "lan_hosts_configured",
        "auth_enabled_by_env", "auth_password_enabled_by_env",
        # P16.1 (D30) — registration switch
        "registration_open",
        # P18.0 (D42/D44) — backup switches + read-only capability status
        "backup_enabled", "backup_retention",
        "backup_supported", "backup_dir_configured",
        # P18.4 (D44) — off-site push switch + whether the backend can hold one
        "backup_offsite", "backup_offsite_supported",
    }
    # D44 default: off — a backup writes files outside the DB, so it is opt-in.
    assert body["backup_enabled"] is False
    assert body["backup_retention"] == 7
    assert body["backup_offsite"] is False
    # The local install is SQLite, so file-snapshot backup is available.
    assert body["backup_supported"] is True
    # ...but the default storage backend is "local", which cannot hold an
    # off-site copy — pushing there would write the file beside the original.
    assert body["backup_offsite_supported"] is False
    # Ceiling status is a boolean — never the configured directory path itself.
    assert "planarus-backups" not in res.text
    # LAN defaults mirror a local install: ceiling off, switch inert-off.
    assert body["lan_permitted_by_env"] is False
    assert body["lan_mode_active"] is False
    # D30 default: open — today's self-registration behavior until closed.
    assert body["registration_open"] is True
    # Ceiling/secret tiers are booleans only — never a raw host, port, or token.
    assert "smtp_host" not in res.text
    assert "smtp_port" not in res.text
    assert "allowed_hosts" not in res.text


def test_put_settings_requires_local_control(client):
    res = client.put("/api/v1/settings", json={"email_enabled": True})
    assert res.status_code == 401


def test_put_settings_roundtrip(client):
    res = client.put(
        "/api/v1/settings",
        headers=local_hdr(client),
        json={"email_enabled": True, "email_from": "ops@example.com"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["email_enabled"] is True
    assert res.json()["email_from"] == "ops@example.com"
    # persisted
    assert client.get("/api/v1/settings").json()["email_from"] == "ops@example.com"


def test_put_settings_ignores_explicit_null(client):
    res = client.put(
        "/api/v1/settings",
        headers=local_hdr(client),
        json={"email_from": None},
    )
    assert res.status_code == 200, res.text
    # null is ignored, not stored — the env default survives, never "None".
    assert res.json()["email_from"] != "None"


def test_put_settings_rejects_unknown_key(client):
    res = client.put(
        "/api/v1/settings",
        headers=local_hdr(client),
        json={"smtp_host": "10.0.0.1"},  # ceiling key — not writable
    )
    assert res.status_code == 422


def test_put_settings_rejects_header_injection_in_from(client):
    res = client.put(
        "/api/v1/settings",
        headers=local_hdr(client),
        json={"email_from": "a@x\nBcc: evil@x"},
    )
    assert res.status_code == 422


# --- external-API switch ------------------------------------------------------


def test_external_switch_off_returns_generic_404(client, external_api):
    """Env ceiling permits the external API; flipping the DB switch off makes the
    surface return the SAME 404 as when it is disabled — not a 401/403 that would
    reveal it exists."""
    ws, proj = seed(client, "sw")
    _, raw = issue_key(client, ws, [proj], can_read=True)

    # default (no Setting row) → ceiling on → external read works
    assert client.get("/api/external/v1/projects", headers=auth(raw)).status_code == 200

    # flip the switch off
    put = client.put(
        "/api/v1/settings", headers=local_hdr(client),
        json={"external_api_active": False},
    )
    assert put.status_code == 200, put.text
    assert put.json()["external_api_active"] is False
    assert put.json()["external_api_permitted_by_env"] is True  # ceiling unchanged

    # same request is now a generic 404
    off = client.get("/api/external/v1/projects", headers=auth(raw))
    assert off.status_code == 404
