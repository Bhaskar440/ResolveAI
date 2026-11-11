"""Application settings.

Loads `.env.local` / `.env` by walking up from this file, then real environment
variables (which always win — that is how docker-compose injects values).
`.env.example` documents every key.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator, model_validator
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
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle_seconds: int = 300

    # demo / fixtures
    fixtures_dir: str = ""
    demo_merchant_slug: str = "northwind"
    demo_merchant_name: str = "Northwind Supply Co."
    demo_user_email: str = "owner@northwind.example"
    demo_user_password: str = "resolveai-demo"
    demo_user_name: str = "Avery Chen"
    demo_user_role: str = "owner"
    # Unset = enabled outside production, disabled in production. The public
    # hackathon deployment sets this to true explicitly (session-guarded routes).
    demo_endpoints_enabled: bool | None = None

    # auth / sessions
    auth_cookie_name: str = "resolveai_session"
    auth_session_hours: int = 12
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"  # lax | strict | none (none requires HTTPS)

    # paypal
    paypal_mode: str = "replay"  # replay | sandbox | mock
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_webhook_verify: bool = True

    # agents
    agent_max_negotiation_rounds: int = 2
    agent_max_tool_calls: int = 12

    # knowledge / RAG
    knowledge_embedding_model: str = "gemini-embedding-001"
    knowledge_embedding_dimensions: int = 768
    knowledge_top_k: int = 6
    knowledge_chunk_chars: int = 1400
    knowledge_chunk_overlap: int = 150

    # llm
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model_fast: str = ""
    llm_model_reasoning: str = ""
    llm_temperature: float = 0.0
    llm_max_output_tokens: int = 900
    llm_timeout_seconds: float = 45.0

    @field_validator("demo_endpoints_enabled", mode="before")
    @classmethod
    def _blank_bool_is_unset(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        """Accept the URL formats managed providers hand out.

        Render/Heroku-style URLs are ``postgres://`` or ``postgresql://`` and
        often carry ``?sslmode=require``. SQLAlchemy's asyncpg dialect needs
        ``postgresql+asyncpg://`` and asyncpg spells the option ``ssl=``.
        """
        if not isinstance(value, str):
            return value
        value = value.strip()
        if value.startswith("postgres://"):
            value = "postgresql+asyncpg://" + value[len("postgres://") :]
        elif value.startswith("postgresql://"):
            value = "postgresql+asyncpg://" + value[len("postgresql://") :]
        value = re.sub(r"([?&])sslmode=", r"\1ssl=", value)
        return value

    @model_validator(mode="after")
    def _validate_production_settings(self) -> "Settings":
        """Fail closed instead of booting a production box with demo secrets."""
        if self.app_env == "production":
            required = {
                "SECRET_KEY": self.secret_key,
                "CREDENTIAL_KEK": self.credential_kek,
                "PII_HASH_PEPPER": self.pii_hash_pepper,
                "PLAN_SIGNING_KEY": self.plan_signing_key,
            }
            missing = [name for name, value in required.items() if len(value) < 32]
            if missing:
                raise ValueError(
                    "APP_ENV=production requires 32+ character values for: "
                    + ", ".join(missing)
                )
            if self.paypal_mode == "sandbox" and not self.paypal_configured:
                raise ValueError(
                    "PAYPAL_MODE=sandbox requires PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET"
                )
        if self.auth_cookie_samesite.lower() not in {"lax", "strict", "none"}:
            raise ValueError("AUTH_COOKIE_SAMESITE must be lax, strict, or none")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def demo_enabled(self) -> bool:
        if self.demo_endpoints_enabled is not None:
            return self.demo_endpoints_enabled
        return self.app_env != "production"

    @property
    def paypal_configured(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_provider and self.llm_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
