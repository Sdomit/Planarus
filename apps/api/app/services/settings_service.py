"""Runtime settings (Phase 9B): a live key/value accessor over the `Setting` table.

The safety model lives in three tiers (see docs/plan/11-settings-and-connections.md):

  * **secret** — SMTP password, API keys, tunnel tokens: stay in env, never here.
  * **ceiling** — env, read once at startup (`external_api_enabled`, allowed hosts,
    SMTP host/port): the UI shows them read-only; a switch can never widen them.
  * **switch** — DB `Setting` rows the UI can flip live (email on/off, from-address,
    external-API "active"). Effective only *within* the env ceiling.

Reads are live (per-request), so a flip takes effect without a restart. Absent
rows fall back to the env value, so env-only deployments behave exactly as today.
"""
import json

from sqlmodel import Session

from app.core.config import settings as env
from app.core.utils import now_utc
from app.models.setting import Setting
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.services.audit_service import create_audit_event

# Switch-tier keys (the only writable ones) are enforced by SettingsUpdate's
# `extra=forbid` schema — no separate allowlist needed here.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def get_setting(session: Session, key: str, default):
    """Return the JSON-decoded switch value, or `default` if unset/corrupt."""
    row = session.get(Setting, key)
    if row is None:
        return default
    try:
        return json.loads(row.value)
    except (ValueError, TypeError):
        return default


def set_setting(session: Session, key: str, value) -> Setting:
    """Upsert one switch row (JSON-encoded). Caller commits."""
    row = session.get(Setting, key)
    encoded = json.dumps(value)
    if row is None:
        row = Setting(key=key, value=encoded, updated_at=now_utc())
        session.add(row)
    else:
        row.value = encoded
        row.updated_at = now_utc()
    return row


def external_api_active(session: Session) -> bool:
    """The external-API DB switch. Default True so an env-only deployment (no row)
    behaves exactly as before — the env ceiling remains the real gate; this can
    only turn a permitted feature *off*."""
    return bool(get_setting(session, "external_api_active", env.external_api_enabled))


def registration_open(session: Session) -> bool:
    """P16.1 (D30): whether password self-registration is accepted. Default True
    (today's open behavior). The provider ceiling (`auth_password_enabled`) is
    enforced separately at the endpoint — this switch can only close the door
    on a permitted provider, never open a disabled one."""
    return bool(get_setting(session, "registration_open", True))


def backup_enabled(session: Session) -> bool:
    """P18.0 (D44): verified local DB backups. Defaults to **False** — unlike the
    other switches this has no env ceiling to inherit, and a backup writes files
    outside the database, so it stays explicitly opt-in."""
    return bool(get_setting(session, "backup_enabled", False))


def backup_retention(session: Session) -> int:
    """How many backups to keep (newest N). Floored at 1 even if a stored row is
    corrupt or out of range, so retention can never be made to delete every copy."""
    try:
        return max(1, int(get_setting(session, "backup_retention", 7)))
    except (TypeError, ValueError):
        return 7


def lan_mode_active(session: Session) -> bool:
    """The LAN-mode DB switch (P11.3). Same contract as external_api_active:
    defaults to the env ceiling, so env-only deployments are unchanged, and it
    can only pause a permitted LAN — never widen past the ceiling (the caller
    ANDs it with ``env.lan_mode_enabled``)."""
    return bool(get_setting(session, "lan_mode_active", env.lan_mode_enabled))


# P11.3: process-local mirror of the LAN switch for the Host-guard middleware,
# which runs on every request and has no request session. Loaded at startup
# (create_app, only when the env ceiling is on) and refreshed by every
# write_settings; per-process state, like rate_limit and presence. None = never
# loaded → fall back to the env ceiling, so env-only deployments are unchanged.
_lan_switch_cache: "bool | None" = None


def lan_switch_cached() -> bool:
    return env.lan_mode_enabled if _lan_switch_cache is None else _lan_switch_cache


def refresh_lan_switch(session: Session) -> None:
    global _lan_switch_cache
    _lan_switch_cache = lan_mode_active(session)


def read_settings(session: Session) -> SettingsRead:
    # Local import: backup_service imports this module for the switch accessors,
    # so importing it at module scope would be a cycle.
    from app.services import backup_service

    return SettingsRead(
        backup_enabled=backup_enabled(session),
        backup_retention=backup_retention(session),
        backup_supported=backup_service.is_supported(session),
        backup_dir_configured=bool((env.backup_dir or "").strip()),
        email_enabled=bool(get_setting(session, "email_enabled", env.email_enabled)),
        email_from=str(get_setting(session, "email_from", env.email_from)),
        external_api_active=bool(
            get_setting(session, "external_api_active", env.external_api_enabled)
        ),
        lan_mode_active=lan_mode_active(session),
        registration_open=registration_open(session),
        external_api_permitted_by_env=env.external_api_enabled,
        external_api_hosts_configured=bool((env.external_api_allowed_hosts or "").strip()),
        email_smtp_loopback=env.smtp_host.strip().lower() in _LOOPBACK_HOSTS,
        lan_permitted_by_env=env.lan_mode_enabled,
        lan_hosts_configured=bool((env.lan_allowed_hosts or "").strip()),
        auth_enabled_by_env=env.auth_enabled,
        auth_password_enabled_by_env=env.auth_password_enabled,
    )


def write_settings(session: Session, data: SettingsUpdate) -> SettingsRead:
    # exclude_none: an explicit JSON null must not be stored (str(None) would
    # otherwise become the literal From address "None").
    changed = data.model_dump(exclude_unset=True, exclude_none=True)
    for key, value in changed.items():
        set_setting(session, key, value)
        # Audit key + value — all switch values are non-secret (bool / from-address).
        create_audit_event(
            session,
            event_type="settings_update",
            actor_type="human",
            entity_type="setting",
            entity_id=key,
            payload_json=json.dumps({"key": key, "value": value}),
        )
    session.commit()
    refresh_lan_switch(session)  # keep the middleware mirror live (P11.3)
    return read_settings(session)
