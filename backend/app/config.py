from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_env: str = "development"
    app_name: str = "BeastInsights AI"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Tenant
    client_id: int = 10042

    # Postgres
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_database: str = "postgres"
    pg_username: str = ""
    pg_password: str = ""
    pg_sslmode: str = "require"

    # Claude / Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Redis (optional — empty string means use in-memory fallback)
    redis_url: str = ""

    def parsed_cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
