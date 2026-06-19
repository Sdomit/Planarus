from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "AgentBoard"
    app_version: str = "0.1.0"
    database_url: str = "sqlite:///./agentboard.db"


settings = Settings()
