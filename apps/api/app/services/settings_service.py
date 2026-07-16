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


def read_settings(session: Session) -> SettingsRead:
    return SettingsRead(
        email_enabled=bool(get_setting(session, "email_enabled", env.email_enabled)),
        email_from=str(get_setting(session, "email_from", env.email_from)),
        external_api_active=bool(
            get_setting(session, "external_api_active", env.external_api_enabled)
        ),
        external_api_permitted_by_env=env.external_api_enabled,
        external_api_hosts_configured=bool((env.external_api_allowed_hosts or "").strip()),
        email_smtp_loopback=env.smtp_host.strip().lower() in _LOOPBACK_HOSTS,
    )


def write_settings(session: Session, data: SettingsUpdate) -> SettingsRead:
    changed = data.model_dump(exclude_unset=True)
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
    return read_settings(session)
