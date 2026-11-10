"""ResolveAI API — application factory and health/meta endpoints.

Run:  uv run uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.base import Base
from app.db.session import SessionLocal, engine

logger = logging.getLogger("resolveai")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
    )
    logger.info("ResolveAI starting | env=%s paypal=%s", settings.app_env, settings.paypal_mode)
    if settings.auto_create_schema and settings.app_env in ("local", "demo"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("schema ensured (%d tables)", len(Base.metadata.tables))
    if not settings.paypal_configured and settings.paypal_mode == "sandbox":
        logger.warning("PAYPAL_MODE=sandbox but credentials are missing — falling back to replay")
    yield
    await engine.dispose()


app = FastAPI(
    title="ResolveAI API",
    version="0.1.0",
    description="Autonomous PayPal dispute resolution — API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", tags=["ops"])
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["ops"])
async def health_ready() -> dict[str, object]:
    db_ok = True
    detail: str | None = None
    try:
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
    except Exception as exc:  # pragma: no cover - depends on infra
        db_ok = False
        detail = str(exc)[:200]
    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "detail": detail,
        "mode": settings.paypal_mode,
        "autonomy_enabled": True,
    }


@app.get("/api/v1/meta", tags=["ops"])
async def meta() -> dict[str, object]:
    """Everything the dashboard header needs in one call."""
    return {
        "app": settings.app_name,
        "env": settings.app_env,
        "paypal_mode": settings.paypal_mode,
        "paypal_configured": settings.paypal_configured,
        "llm_provider": settings.llm_provider or None,
        "llm_configured": settings.llm_configured,
        "capabilities": {
            "live_paypal": settings.paypal_configured and settings.paypal_mode == "sandbox",
            "agents": settings.llm_configured,
            "replay": True,
        },
    }
