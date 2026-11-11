from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.db.models import AgentRun, Approval, Dispute, Refund
from app.schemas.responses import Metrics

router = APIRouter(prefix="/metrics", tags=["metrics"])

OPEN_STATES = ("RECEIVED", "ANALYZING", "AWAITING_INFO", "AWAITING_APPROVAL", "REFUND_PENDING")


@router.get("", response_model=Metrics)
async def metrics(session: SessionDep) -> Metrics:
    rows = (
        await session.execute(select(Dispute.status, func.count()).group_by(Dispute.status))
    ).all()
    counts = {status: count for status, count in rows}

    at_risk = (
        await session.execute(
            select(func.coalesce(func.sum(Dispute.amount), 0)).where(
                Dispute.status.in_(OPEN_STATES)
            )
        )
    ).scalar_one()
    recovered = (
        await session.execute(
            select(func.coalesce(func.sum(Refund.amount), 0)).where(
                Refund.status == "COMPLETED"
            )
        )
    ).scalar_one()
    auto_executed = (
        await session.execute(
            select(func.count()).select_from(Refund).where(Refund.initiated_by == "agent")
        )
    ).scalar_one()
    human_executed = (
        await session.execute(
            select(func.count()).select_from(Refund).where(Refund.initiated_by == "human")
        )
    ).scalar_one()
    pending_approvals = (
        await session.execute(
            select(func.count()).select_from(Approval).where(Approval.status == "pending")
        )
    ).scalar_one()
    by_reason_rows = (
        await session.execute(
            select(Dispute.reason_code, func.count()).group_by(Dispute.reason_code)
        )
    ).all()

    durations = (
        (
            await session.execute(
                select(AgentRun.started_at, AgentRun.ended_at).where(
                    AgentRun.ended_at.is_not(None), AgentRun.started_at.is_not(None)
                )
            )
        )
        .all()
    )
    seconds = sorted(
        (ended - started).total_seconds()
        for started, ended in durations
        if started is not None and ended is not None
    )
    median = None
    if seconds:
        mid = len(seconds) // 2
        median = (
            seconds[mid]
            if len(seconds) % 2
            else round((seconds[mid - 1] + seconds[mid]) / 2, 2)
        )

    return Metrics(
        open_disputes=sum(counts.get(s, 0) for s in OPEN_STATES),
        awaiting_approval=counts.get("AWAITING_APPROVAL", 0),
        resolved=counts.get("RESOLVED", 0),
        escalated=counts.get("ESCALATED", 0),
        pending_approvals=pending_approvals,
        total_at_risk=Decimal(str(at_risk)).quantize(Decimal("0.01")),
        recovered=Decimal(str(recovered)).quantize(Decimal("0.01")),
        auto_executed=auto_executed,
        human_executed=human_executed,
        median_run_seconds=median,
        by_reason={reason: count for reason, count in by_reason_rows},
    )
