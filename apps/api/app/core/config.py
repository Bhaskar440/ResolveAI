"""Application settings.

Loads `.env.local` / `.env` by walking up from this file, then real environment
variables (which always win — that is how docker-compose injects values).
`.env.example` documents every key.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_HERE = Path(__file__).resolve()


def _discover_env_files() -> tuple[Path, ...]:
    """Nearest .env.local / .env going up the tree; empty when none exist.

    Container layouts put the app at /app (no repo root), so this must not assume
    a fixed depth.
    """
    found: list[Path] = []
    for parent in _HERE.parents:
        for name in (".env.local", ".env"):
            candidate = parent / name
            if candidate.exists() and candidate not in found:
                found.append(candidate)
    return tuple(found[:4])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_discover_env_files(),
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
    database_url: str = "postgresql+asyncpg://resolveai:resolveai@localhost:55433/resolveai"
    db_echo: bool = False

    # demo / fixtures
    fixtures_dir: str = ""
    demo_merchant_slug: str = "northwind"
    demo_merchant_name: str = "Northwind Supply Co."

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
    llm_temperature: float = 0.0
    llm_max_output_tokens: int = 900
    llm_timeout_seconds: float = 45.0

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
