from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AgentBoard"
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./agentboard.db"

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


settings = Settings()
