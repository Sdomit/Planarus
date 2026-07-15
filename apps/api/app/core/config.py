from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Approvo"
    app_version: str = "0.1.0"
    # P10.0: env-overridable so the app (and Alembic, which reads this field via
    # alembic/env.py) can target Postgres without a code change. AGENTBOARD_* wins
    # over the platform-conventional DATABASE_URL when both are set.
    database_url: str = Field(
        default="sqlite:///./agentboard.db",
        validation_alias=AliasChoices("AGENTBOARD_DATABASE_URL", "DATABASE_URL"),
    )

    # Phase 7C1 external HTTP API. DISABLED by default; when off, every
    # /api/external/v1 route returns a generic not_found. Per-field env aliases are
    # used (not a global env_prefix) so the existing fields' resolution is untouched.
    external_api_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_EXTERNAL_API_ENABLED"
    )
    # Optional comma-separated extra Host-header values for a deliberate, documented
    # non-loopback deployment. Empty (default) → only loopback hosts are accepted.
    external_api_allowed_hosts: str = Field(
        default="", validation_alias="AGENTBOARD_EXTERNAL_API_ALLOWED_HOSTS"
    )

    # Phase 9 email reminders. DISABLED by default; when enabled, sends go only to
    # a loopback SMTP host (Mailpit) — the service refuses any non-loopback host.
    email_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_EMAIL_ENABLED"
    )
    smtp_host: str = Field(default="127.0.0.1", validation_alias="AGENTBOARD_SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="AGENTBOARD_SMTP_PORT")
    email_from: str = Field(
        default="agentboard@localhost", validation_alias="AGENTBOARD_EMAIL_FROM"
    )

    # Phase 10.1 (hosted mode) — identity/auth. DISABLED by default: when off, the
    # /api/v1/auth/* and workspace members routes 404 and the app is the same
    # local single-user tool it has always been. Only a hosted deployment turns
    # this on. No tenant enforcement on existing domain routes yet (that is P10.2).
    auth_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_AUTH_ENABLED"
    )
    # The password-less "dev" identity provider (get-or-create login) for local
    # bootstrap + tests. Doubly-gated: ignored unless auth_enabled is ALSO true.
    # NEVER enable in a real hosted deployment — it is an unauthenticated
    # account-creation path by design.
    auth_dev_login_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_AUTH_DEV_LOGIN"
    )
    # Server-side session lifetime in hours (default 30 days).
    auth_session_ttl_hours: int = Field(
        default=720, validation_alias="AGENTBOARD_AUTH_SESSION_TTL_HOURS"
    )

    # Phase 10.3 (hosted mode) — storage backend for generated project artifacts.
    # "local" (default) is the filesystem, byte-identical to before. "memory" is
    # for tests/ephemeral use. A hosted "s3" adapter is a future addition.
    storage_backend: str = Field(
        default="local", validation_alias="AGENTBOARD_STORAGE_BACKEND"
    )

    # Phase 10.4 (hosted deploy) — extra allowed browser origins for the hosted
    # web app, comma-separated (e.g. "https://app.example.com"). Empty (default)
    # means only the local dev origins are trusted, so nothing changes locally.
    # These are added to the CORS allowlist and the Origin check for the local
    # control-token endpoints.
    web_origins: str = Field(default="", validation_alias="AGENTBOARD_WEB_ORIGINS")


settings = Settings()
