from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://smart_home:smart_home@localhost:5432/smart_home"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_seconds: int = 86400
    cors_origins: str = "*"
    seed_enabled: bool = True
    sim_enabled: bool = False
    run_migrations_on_start: bool = False


settings = Settings()
