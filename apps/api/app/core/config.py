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

    # Phase 12b explicit fetch. DISABLED by default. This is the SOLE documented
    # exception to the "SHOW, DON'T DO" no-mutation rule: a human-clicked fetch
    # that updates remote-tracking refs + FETCH_HEAD only (working tree untouched).
    # Never auto-fetches; the endpoint is additionally control-token-gated.
    git_fetch_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_GIT_FETCH_ENABLED"
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
    # P11.1 (D25) — the local email+password provider, the LAN-mode identity
    # method (OAuth needs a public redirect URI a LAN box doesn't have). Doubly-
    # gated like dev-login: ignored unless auth_enabled is ALSO true. Off by
    # default so enabling hosted auth never silently opens a password surface.
    auth_password_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_AUTH_PASSWORD_ENABLED"
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
    # P10.3b — S3 backend config (used only when storage_backend == "s3").
    storage_s3_bucket: str = Field(default="", validation_alias="AGENTBOARD_S3_BUCKET")
    storage_s3_prefix: str = Field(default="", validation_alias="AGENTBOARD_S3_PREFIX")
    storage_s3_region: str = Field(default="", validation_alias="AGENTBOARD_S3_REGION")
    storage_s3_endpoint_url: str = Field(
        default="", validation_alias="AGENTBOARD_S3_ENDPOINT_URL"
    )

    # Phase 10.4 (hosted deploy) — extra allowed browser origins for the hosted
    # web app, comma-separated (e.g. "https://app.example.com"). Empty (default)
    # means only the local dev origins are trusted, so nothing changes locally.
    # These are added to the CORS allowlist and the Origin check for the local
    # control-token endpoints.
    web_origins: str = Field(default="", validation_alias="AGENTBOARD_WEB_ORIGINS")

    # Phase 10.1b — real OAuth providers. A provider is only available when its
    # client id is set; unset (default) → its routes 404. Secrets are never logged
    # or returned. Requires the optional [oauth] extra (httpx) at runtime.
    oauth_google_client_id: str = Field(
        default="", validation_alias="AGENTBOARD_OAUTH_GOOGLE_CLIENT_ID"
    )
    oauth_google_client_secret: str = Field(
        default="", validation_alias="AGENTBOARD_OAUTH_GOOGLE_CLIENT_SECRET"
    )
    oauth_github_client_id: str = Field(
        default="", validation_alias="AGENTBOARD_OAUTH_GITHUB_CLIENT_ID"
    )
    oauth_github_client_secret: str = Field(
        default="", validation_alias="AGENTBOARD_OAUTH_GITHUB_CLIENT_SECRET"
    )

    # Phase 15.12b — calendar external sync (Google/Microsoft). Fully inert unless
    # BOTH an encryption key AND a provider client id are set: no key → tokens can't
    # be stored → sync routes 404; no client id → that provider is unavailable.
    # Distinct from the login OAuth above (different scopes: offline calendar access).
    # Secrets/key live only in the environment (a forbidden path) and are never
    # logged or returned. Requires the optional [calendar-sync] extra at runtime.
    calendar_enc_key: str = Field(
        default="", validation_alias="AGENTBOARD_CALENDAR_ENC_KEY"
    )
    calendar_google_client_id: str = Field(
        default="", validation_alias="AGENTBOARD_CALENDAR_GOOGLE_CLIENT_ID"
    )
    calendar_google_client_secret: str = Field(
        default="", validation_alias="AGENTBOARD_CALENDAR_GOOGLE_CLIENT_SECRET"
    )
    calendar_microsoft_client_id: str = Field(
        default="", validation_alias="AGENTBOARD_CALENDAR_MICROSOFT_CLIENT_ID"
    )
    calendar_microsoft_client_secret: str = Field(
        default="", validation_alias="AGENTBOARD_CALENDAR_MICROSOFT_CLIENT_SECRET"
    )

    # Phase 11.0 (LAN team mode) — ceiling env vars, DISABLED by default. When
    # off, nothing changes: the app-wide Host allowlist stays loopback (plus any
    # 7C1 external hosts). When on, the allowlist additionally accepts the
    # comma-separated LAN hosts below — and create_app() refuses to start unless
    # auth is ALSO enabled (fail closed, D25): the local control token is not an
    # identity, so widening the host boundary without per-user auth would expose
    # the whole DB to the network. The app itself never binds beyond loopback;
    # the actual socket bind stays the user's explicit uvicorn choice (D26 —
    # plain HTTP on the LAN is a documented, warned-about tradeoff).
    lan_mode_enabled: bool = Field(
        default=False, validation_alias="AGENTBOARD_LAN_MODE_ENABLED"
    )
    lan_allowed_hosts: str = Field(
        default="", validation_alias="AGENTBOARD_LAN_ALLOWED_HOSTS"
    )


settings = Settings()
