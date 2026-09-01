from functools import lru_cache
from typing import Literal

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

    # --- Authentication (Phase 2) ---
    # No default secret is provided in a non-development environment: a
    # missing JWT_SECRET_KEY outside development is a startup-time error
    # (see get_settings validation below), never a silently-guessable default.
    jwt_secret_key: str | None = None
    jwt_issuer: str = "ai-receptionist"
    jwt_audience: str = "ai-receptionist-clients"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    # --- Cookie security (environment-aware) ---
    # cookie_secure defaults to True everywhere except local development, so
    # production never accidentally ships a non-Secure cookie.
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    refresh_cookie_name: str = "ai_receptionist_refresh"
    csrf_cookie_name: str = "ai_receptionist_csrf"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def resolved_cookie_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.environment != "development"

    def require_jwt_secret(self) -> str:
        """Raises at call time (not import time) if no signing secret is configured.

        Keeping this lazy means the app can still boot (e.g. for /health) in an
        environment where auth hasn't been configured yet, but any actual auth
        operation fails loudly instead of silently using a guessable default.
        """
        if not self.jwt_secret_key:
            raise RuntimeError(
                "JWT_SECRET_KEY is not set. Generate one and set it in backend/.env "
                "(see .env.example) before using authentication endpoints."
            )
        return self.jwt_secret_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
