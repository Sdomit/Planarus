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


settings = Settings()
