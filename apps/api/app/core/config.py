"""Application settings (env-driven, NEXUS_ prefix)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/config.py -> parents[4] == repo root (nexus/)
ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEXUS_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str | None = None          # None -> local SQLite
    secret_key: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 8

    llm_provider: str = "mock"               # mock | openai | anthropic | gemini
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None

    embed_provider: str = "hash"             # hash | openai
    embed_model: str = "text-embedding-3-small"
    # Postgres path only: store/serve vectors via pgvector instead of the
    # in-process numpy store (needs CREATE EXTENSION vector permission).
    use_pgvector: bool = False

    max_upload_bytes: int = 10 * 1024 * 1024
    upload_dir: str = str(ROOT / "data" / "processed" / "uploads")
    worker_threads: int = 2
    auth_rate_limit: int = 30                # per-IP per minute (auth endpoints)

    @property
    def db_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{ROOT / 'data' / 'processed' / 'nexus.db'}"

    @property
    def using_postgres(self) -> bool:
        return self.db_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    return Settings()
