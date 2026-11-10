"""Demo helpers — seeding and reset. Disabled when APP_ENV=production."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import delete, func, select

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.db.models import (
    AgentMessage,
    AgentRun,
    AgentStep,
    Approval,
    AuditLog,
    Capture,
    Decision,
    Dispute,
    DisputeMessage,
    DisputeStatusHistory,
    EvidenceFile,
    Merchant,
    Order,
    OutboxEvent,
    PolicyEvaluation,
    Refund,
    WebhookDelivery,
)
from app.paypal.factory import get_adapter
from app.paypal.replay import ReplayAdapter
from app.schemas.responses import SeedResult
from app.services.ingestion import get_or_create_merchant, sync_all

router = APIRouter(prefix="/demo", tags=["demo"])
settings = get_settings()


def _guard() -> None:
    if settings.app_env == "production":
        raise NotFoundError("Demo endpoints are disabled in production.")


@router.post("/seed", response_model=SeedResult)
async def seed(session: SessionDep) -> SeedResult:
    _guard()
    before = (await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
    merchant = await get_or_create_merchant(session)
    disputes = await sync_all(session)
    adapter = get_adapter()
    return SeedResult(
        merchant=merchant.slug,
        disputes=len(disputes),
        mode=adapter.mode,
        created=(await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
        > before,
    )


@router.get("/config")
async def demo_config() -> dict:
    _guard()
    adapter = get_adapter()
    return {
        "mode": adapter.mode,
        "fixtures_version": adapter.fixtures_version()
        if isinstance(adapter, ReplayAdapter)
        else None,
        "app_env": settings.app_env,
        "llm_model_fast": settings.llm_model_fast,
        "llm_model_reasoning": settings.llm_model_reasoning,
        "llm_configured": settings.llm_configured,
        "paypal_configured": settings.paypal_configured,
    }


@router.post("/reset")
async def reset(session: SessionDep) -> dict:
    _guard()
    for model in (
        Approval,
        Decision,
        PolicyEvaluation,
        AgentMessage,
        AgentStep,
        AgentRun,
        Refund,
        DisputeMessage,
        DisputeStatusHistory,
        EvidenceFile,
        WebhookDelivery,
        OutboxEvent,
        AuditLog,
        Dispute,
        Capture,
        Order,
    ):
        await session.execute(delete(model))
    await session.commit()
    remaining = (await session.execute(select(func.count()).select_from(Merchant))).scalar_one()
    return {"status": "reset", "merchants_kept": remaining}
