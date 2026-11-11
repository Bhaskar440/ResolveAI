from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.db.models import AgentRun, Approval, Dispute, Refund
from app.schemas.responses import (
    Analytics,
    Metrics,
    ReasonBreakdown,
    RefundSummary,
    StatusCount,
    TrendPoint,
)

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


@router.get("/analytics", response_model=Analytics)
async def analytics(session: SessionDep) -> Analytics:
    """Rich aggregates for the analytics page, computed from live rows."""
    disputes = (await session.execute(select(Dispute))).scalars().all()
    refund_rows = (await session.execute(select(Refund))).scalars().all()
    run_rows = (
        (
            await session.execute(
                select(AgentRun.started_at, AgentRun.ended_at).where(
                    AgentRun.ended_at.is_not(None), AgentRun.started_at.is_not(None)
                )
            )
        )
        .all()
    )

    status_counts: dict[str, int] = defaultdict(int)
    reason_counts: dict[str, int] = defaultdict(int)
    reason_at_risk: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    reason_resolved: dict[str, int] = defaultdict(int)
    reason_refunded: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    total_at_risk = Decimal(0)
    resolved_cases = 0
    escalated_cases = 0
    awaiting_approval = 0

    for dispute in disputes:
        status_counts[dispute.status] += 1
        reason_counts[dispute.reason_code] += 1
        if dispute.status in OPEN_STATES:
            total_at_risk += dispute.amount
            reason_at_risk[dispute.reason_code] += dispute.amount
        if dispute.status == "RESOLVED":
            resolved_cases += 1
            reason_resolved[dispute.reason_code] += 1
        if dispute.status == "ESCALATED":
            escalated_cases += 1
        if dispute.status == "AWAITING_APPROVAL":
            awaiting_approval += 1

    refunded_total = Decimal(0)
    refund_completed = 0
    refund_pending = 0
    refund_failed = 0
    refund_simulated = 0
    refund_live = 0
    simulated_total = Decimal(0)
    by_dispute_refunds: dict = defaultdict(lambda: Decimal(0))
    for refund in refund_rows:
        amount = refund.amount or Decimal(0)
        simulated = bool((refund.raw or {}).get("simulated"))
        if refund.status == "COMPLETED":
            refund_completed += 1
            refunded_total += amount
            if refund.dispute_id:
                by_dispute_refunds[refund.dispute_id] += amount
        elif refund.status in {"PENDING", "PROCESSING"}:
            refund_pending += 1
        elif refund.status in {"FAILED", "DENIED", "CANCELLED"}:
            refund_failed += 1
        if simulated:
            refund_simulated += 1
            simulated_total += amount
        else:
            refund_live += 1

    for dispute in disputes:
        if dispute.id in by_dispute_refunds:
            reason_refunded[dispute.reason_code] += by_dispute_refunds[dispute.id]

    days = 14
    today = datetime.now(UTC).date()
    start_day = today - timedelta(days=days - 1)
    created_by_day: dict[date, int] = defaultdict(int)
    resolved_by_day: dict[date, int] = defaultdict(int)
    for dispute in disputes:
        if dispute.created_at:
            created_by_day[dispute.created_at.date()] += 1
        if dispute.resolved_at:
            resolved_by_day[dispute.resolved_at.date()] += 1
    trend = []
    for index in range(days):
        day = start_day + timedelta(days=index)
        trend.append(
            TrendPoint(
                date=day.isoformat(),
                created=created_by_day.get(day, 0),
                resolved=resolved_by_day.get(day, 0),
            )
        )

    seconds = sorted(
        (ended - started).total_seconds()
        for started, ended in run_rows
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

    total = len(disputes)
    return Analytics(
        total_disputes=total,
        resolved_cases=resolved_cases,
        pending_cases=sum(status_counts.get(s, 0) for s in OPEN_STATES),
        escalated_cases=escalated_cases,
        awaiting_approval=awaiting_approval,
        resolution_rate=round(resolved_cases / total * 100, 1) if total else 0.0,
        total_at_risk=total_at_risk.quantize(Decimal("0.01")),
        refunded_total=refunded_total.quantize(Decimal("0.01")),
        by_status=[
            StatusCount(status=status, count=count)
            for status, count in sorted(status_counts.items())
        ],
        by_reason=[
            ReasonBreakdown(
                reason_code=reason,
                count=reason_counts[reason],
                at_risk=reason_at_risk[reason].quantize(Decimal("0.01")),
                resolved=reason_resolved[reason],
                refunded=reason_refunded[reason].quantize(Decimal("0.01")),
            )
            for reason in sorted(reason_counts, key=lambda r: (-reason_counts[r], r))
        ],
        refunds=RefundSummary(
            count=len(refund_rows),
            completed=refund_completed,
            pending=refund_pending,
            failed=refund_failed,
            simulated=refund_simulated,
            live=refund_live,
            amount_total=sum((r.amount or Decimal(0)) for r in refund_rows).quantize(
                Decimal("0.01")
            ),
            amount_completed=refunded_total.quantize(Decimal("0.01")),
            amount_simulated=simulated_total.quantize(Decimal("0.01")),
        ),
        trend=trend,
        median_run_seconds=median,
    )
