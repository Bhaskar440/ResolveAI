"""ResolveAI API — application factory.

Run locally:  uv run uvicorn app.main:app --reload --port 8000
Schema is owned by Alembic:  uv run alembic upgrade head
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.db import models  # noqa: F401  (registers tables on Base.metadata)
from app.db.session import SessionLocal, engine

settings = get_settings()
logger = logging.getLogger("resolveai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)
    logger.info(
        "starting | env=%s mode=%s db=%s",
        settings.app_env,
        settings.paypal_mode,
        _safe_db_target(settings.database_url),
    )
    if settings.paypal_mode == "sandbox" and not settings.paypal_configured:
        logger.warning("PAYPAL_MODE=sandbox without credentials — live calls will fail closed")
    if settings.paypal_mode == "replay":
        logger.info("replay mode: PayPal calls are served from fixtures/ (no network)")
    try:
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
        logger.info("database connection ok")
    except Exception as exc:
        logger.error("database connection FAILED: %s", str(exc).splitlines()[0][:200])
    yield
    await engine.dispose()
    logger.info("shutdown complete")


def _safe_db_target(url: str) -> str:
    """Log host/db but never the password."""
    try:
        tail = url.split("@", 1)[1]
        return f"...@{tail}"
    except IndexError:
        return url


app = FastAPI(
    title="ResolveAI API",
    version="0.1.0",
    description="Autonomous PayPal dispute resolution — API",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time-Ms"],
)
app.add_middleware(RequestContextMiddleware)  # outermost: correlates everything
register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health/live", tags=["ops"])
async def health_live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", tags=["ops"])
async def health_ready():
    try:
        async with SessionLocal() as session:
            await session.execute(text("select 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": False, "detail": str(exc).splitlines()[0][:200]},
        )
    return {"status": "ok", "db": True, "mode": settings.paypal_mode}
