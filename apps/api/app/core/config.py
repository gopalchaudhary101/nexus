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
    environment: str = "development"         # development | production
    # Comma-separated browser origins allowed to call the API. The "*"
    # default is fine for local dev (no cookies are used, so wildcard CORS
    # carries no credential-leak risk here) but should be pinned to the
    # real frontend origin(s) in production — see docs/security.md.
    cors_origins: str = "*"

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def assert_production_safe(self) -> None:
        """Fail closed instead of booting a production deployment with a
        forgeable JWT signing key. Without this, `secret_key`'s insecure
        default (checked into .env.example for local dev) would let anyone
        mint a valid access token for any user id."""
        if self.environment == "production" and self.secret_key == "dev-secret-change-me":
            raise RuntimeError(
                "NEXUS_SECRET_KEY is still the insecure default while "
                "NEXUS_ENVIRONMENT=production. Set a real secret "
                "(python -c \"import secrets; print(secrets.token_urlsafe(48))\")."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
