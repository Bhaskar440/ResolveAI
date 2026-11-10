"""Application settings.

Loads from the repo-root `.env.local` (git-ignored), then real environment variables
(which win). `.env.example` documents every key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# apps/api/app/core/config.py -> parents[4] == repo root
ROOT_DIR = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env.local", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # app
    app_env: str = "local"
    app_name: str = "ResolveAI"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # secrets (blank in .env.example; generated into .env.local)
    secret_key: str = ""
    credential_kek: str = ""
    pii_hash_pepper: str = ""
    plan_signing_key: str = ""

    # db
    database_url: str = "postgresql+asyncpg://resolveai:resolveai@localhost:5432/resolveai"
    db_echo: bool = False
    auto_create_schema: bool = True

    # paypal
    paypal_mode: str = "replay"  # replay | sandbox | mock
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_webhook_verify: bool = True

    # llm
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model_fast: str = ""
    llm_model_reasoning: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_provider and self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
