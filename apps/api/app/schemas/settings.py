from typing import Optional

from pydantic import BaseModel, field_validator


class SettingsRead(BaseModel):
    """Everything the Settings page shows. Switch tier is editable; the ceiling/
    secret tiers are boolean status only — never a raw host, port, key, or token."""

    # --- switch tier (editable, stored as DB Setting rows) ---
    email_enabled: bool
    email_from: str
    external_api_active: bool
    lan_mode_active: bool  # P11.3: pause LAN acceptance within the env ceiling
    registration_open: bool  # P16.1 (D30): accept password self-registration
    # --- ceiling tier (env-owned, read-only status) ---
    external_api_permitted_by_env: bool
    external_api_hosts_configured: bool
    email_smtp_loopback: bool
    # P11.3 (LAN team mode section) — booleans only, never raw hosts.
    lan_permitted_by_env: bool
    lan_hosts_configured: bool
    auth_enabled_by_env: bool
    auth_password_enabled_by_env: bool


class SettingsUpdate(BaseModel):
    """Only switch-tier keys are writable. Unknown keys are rejected by Pydantic."""

    model_config = {"extra": "forbid"}

    email_enabled: Optional[bool] = None
    email_from: Optional[str] = None
    external_api_active: Optional[bool] = None
    lan_mode_active: Optional[bool] = None
    registration_open: Optional[bool] = None

    @field_validator("email_from")
    @classmethod
    def _valid_from(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        # Trust boundary: this becomes an email From header — no header injection,
        # bounded length, must look like an address.
        if not v or len(v) > 254 or "\n" in v or "\r" in v or "@" not in v:
            raise ValueError("email_from must be a single-line address under 254 chars")
        return v
