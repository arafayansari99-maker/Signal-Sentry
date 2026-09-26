import os
import tempfile
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    if os.getenv("VERCEL"):
        database_path = Path(tempfile.gettempdir()) / "competitive_intelligence.db"
        return f"sqlite:///{database_path.as_posix()}"
    return "sqlite:///./competitive_intelligence.db"


class Settings(BaseSettings):
    app_name: str = "competitive-intelligence-agent"
    environment: str = "development"
    database_url: str = Field(default_factory=_default_database_url)
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "monitoring"
    background_queue_enabled: bool = True
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    sentry_dsn: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "claude-3-5-sonnet"
    monitoring_cron_schedule: str = "0 9 * * *"
    monitoring_interval_minutes: int = 300
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    slack_webhook_url: str | None = None
    alert_email_to: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
