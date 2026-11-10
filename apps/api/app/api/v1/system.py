"""System status — the endpoint the dashboard uses to prove the whole stack is live.

No cached values, no hardcoded numbers: every field is measured on the request.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select, text

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.logging import request_id_ctx
from app.db.models import AgentRun, Dispute, Refund
from app.schemas.responses import Counts, DBStatus, SystemStatus

router = APIRouter(tags=["system"])
logger = logging.getLogger("resolveai.system")
settings = get_settings()


@router.get("/status", response_model=SystemStatus)
async def system_status(session: SessionDep) -> SystemStatus:
    started = time.perf_counter()
    db = DBStatus(connected=False, latency_ms=0.0)

    try:
        version = (await session.execute(text("select version()"))).scalar_one()
        tables = (
            await session.execute(
                text(
                    "select count(*) from information_schema.tables "
                    "where table_schema = 'public' and table_type = 'BASE TABLE'"
                )
            )
        ).scalar_one()
        disputes = (await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
        runs = (await session.execute(select(func.count()).select_from(AgentRun))).scalar_one()
        refunds = (await session.execute(select(func.count()).select_from(Refund))).scalar_one()
        db = DBStatus(
            connected=True,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            server_version=str(version).split(",")[0],
        )
        counts = Counts(disputes=disputes, runs=runs, refunds=refunds)
    except Exception as exc:  # DB down / not migrated — report it, never pretend
        logger.warning("database check failed: %s", exc)
        db = DBStatus(
            connected=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            error=str(exc).splitlines()[0][:200],
        )
        counts = Counts()
        tables = 0

    return SystemStatus(
        status="ok" if db.connected else "degraded",
        app=settings.app_name,
        env=settings.app_env,
        mode=settings.paypal_mode,
        checked_at=datetime.now(UTC),
        db=db,
        counts=counts,
        schema_tables=int(tables),
        capabilities={
            "paypal_credentials": settings.paypal_configured,
            "live_paypal": settings.paypal_configured and settings.paypal_mode == "sandbox",
            "agents": settings.llm_configured,
            "replay": True,
        },
        request_id=request_id_ctx.get(),
    )
