from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven application configuration.

    No credentials are hardcoded here. DATABASE_URL is optional so the
    service can boot and report health even before a database is provisioned.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI Receptionist API"
    environment: str = "development"
    debug: bool = True

    database_url: str | None = None

    cors_allow_origins: str = "http://localhost:3000"

    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
