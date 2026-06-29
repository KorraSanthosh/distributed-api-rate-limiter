import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Base system settings using Pydantic Settings."""

    ENV: str = "dev"
    DEBUG: bool = True
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Redis Configurations
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_TIMEOUT: float = 2.0
    REDIS_MAX_CONNECTIONS: int = 50

    # Rate Limiting Configurations (Defaults)
    # The default window size in seconds
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    # The default maximum requests allowed in the window
    RATE_LIMIT_MAX_REQUESTS: int = 60
    # The default burst limit (absolute ceiling for short spikes)
    RATE_LIMIT_BURST_LIMIT: int = 80

    # Observability
    PROMETHEUS_PORT: int = 9000
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "logs/app.json"
    LOG_MAX_BYTES: int = 10485760  # 10MB
    LOG_BACKUP_COUNT: int = 5

    # API documentation settings
    PROJECT_NAME: str = "Distributed Rate Limiter & Traffic Analyzer"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


class DevSettings(Settings):
    """Settings used in development mode."""

    ENV: str = "dev"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"


class ProdSettings(Settings):
    """Settings used in production mode."""

    ENV: str = "prod"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"


class TestSettings(Settings):
    """Settings used during test suites."""

    ENV: str = "test"
    DEBUG: bool = True
    REDIS_DB: int = 9  # Use a dedicated DB for tests to prevent data collision
    REDIS_TIMEOUT: float = 0.5
    LOG_LEVEL: str = "WARNING"
    RATE_LIMIT_WINDOW_SECONDS: int = 5
    RATE_LIMIT_MAX_REQUESTS: int = 3
    RATE_LIMIT_BURST_LIMIT: int = 5


def get_settings() -> Settings:
    """Factory function to fetch settings based on the current environment."""
    env = os.getenv("ENV", "dev").lower()
    if env == "prod":
        return ProdSettings()
    elif env == "test":
        return TestSettings()
    return DevSettings()


settings = get_settings()
