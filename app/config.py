from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "competitive-intelligence-agent"
    environment: str = "development"
    database_url: str = "sqlite:///./competitive_intelligence.db"
    jwt_secret_key: str = "signalsentry-company-auth-secret"
    jwt_algorithm: str = "HS256"
    redis_url: str = "redis://localhost:6379/0"
    redis_queue_name: str = "monitoring"
    background_queue_enabled: bool = True
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
