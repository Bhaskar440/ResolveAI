from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import SessionDep, require_session
from app.core.errors import NotFoundError, ValidationError
from app.db.models import (
    AgentRun,
    Approval,
    Capture,
    Decision,
    Dispute,
    DisputeMessage,
    Order,
    PolicyEvaluation,
    Refund,
)
from app.schemas.responses import (
    ApprovalOut,
    CaptureOut,
    DecisionOut,
    DisputeDetail,
    DisputeList,
    DisputeOut,
    MessageCreate,
    MessageOut,
    OrderOut,
    PolicyEvalOut,
    RefundOut,
    RunOut,
)
from app.services.orchestrator import run_dispute

router = APIRouter(prefix="/disputes", tags=["disputes"])

SORTABLE = {
    "response_due_by": Dispute.response_due_by,
    "amount": Dispute.amount,
    "created_at": Dispute.created_at,
    "updated_at": Dispute.updated_at,
    "confidence": Dispute.confidence,
    "status": Dispute.status,
}


@router.get("", response_model=DisputeList)
async def list_disputes(
    session: SessionDep,
    status: str | None = Query(None, description="comma-separated statuses"),
    reason: str | None = None,
    q: str | None = Query(None, description="case number / buyer / reason search"),
    sort: str = Query("response_due_by:asc"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DisputeList:
    stmt = select(Dispute)
    count_stmt = select(func.count()).select_from(Dispute)

    filters = []
    if status:
        wanted = [s.strip().upper() for s in status.split(",") if s.strip()]
        if wanted:
            filters.append(Dispute.status.in_(wanted))
    if reason:
        filters.append(Dispute.reason_code == reason)
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(
                Dispute.paypal_case_number.ilike(like),
                Dispute.paypal_dispute_id.ilike(like),
                Dispute.buyer_label.ilike(like),
                Dispute.reason_code.ilike(like),
            )
        )
    for f in filters:
        stmt = stmt.where(f)
        count_stmt = count_stmt.where(f)

    field, _, direction = sort.partition(":")
    column = SORTABLE.get(field, Dispute.response_due_by)
    stmt = stmt.order_by(column.desc() if direction.lower() == "desc" else column.asc().nulls_last())

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (await session.execute(stmt.limit(limit).offset(offset))).scalars().all()
    return DisputeList(
        items=[DisputeOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{dispute_id}", response_model=DisputeDetail)
async def get_dispute(dispute_id: UUID, session: SessionDep) -> DisputeDetail:
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == dispute_id))
    ).scalar_one_or_none()
    if dispute is None:
        raise NotFoundError(f"Dispute {dispute_id} does not exist.")

    order = (
        (await session.execute(select(Order).where(Order.id == dispute.order_id))).scalar_one_or_none()
        if dispute.order_id
        else None
    )
    capture = (
        (
            await session.execute(select(Capture).where(Capture.id == dispute.capture_id))
        ).scalar_one_or_none()
        if dispute.capture_id
        else None
    )
    messages = (
        (
            await session.execute(
                select(DisputeMessage)
                .where(DisputeMessage.dispute_id == dispute.id)
                .order_by(DisputeMessage.sent_at.asc().nulls_last(), DisputeMessage.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    latest_run = (
        (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.dispute_id == dispute.id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    decision = (
        (
            await session.execute(
                select(Decision)
                .where(Decision.dispute_id == dispute.id)
                .order_by(Decision.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    approvals = (
        (
            await session.execute(
                select(Approval)
                .where(Approval.dispute_id == dispute.id)
                .order_by(Approval.requested_at.desc())
            )
        )
        .scalars()
        .all()
    )
    refunds = (
        (
            await session.execute(
                select(Refund)
                .where(Refund.dispute_id == dispute.id)
                .order_by(Refund.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    policy_eval = (
        (
            await session.execute(
                select(PolicyEvaluation)
                .where(PolicyEvaluation.dispute_id == dispute.id)
                .order_by(PolicyEvaluation.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    return DisputeDetail(
        dispute=DisputeOut.model_validate(dispute),
        order=OrderOut.model_validate(order) if order else None,
        capture=CaptureOut.model_validate(capture) if capture else None,
        messages=[MessageOut.model_validate(m) for m in messages],
        latest_run=RunOut.model_validate(latest_run) if latest_run else None,
        decision=DecisionOut.model_validate(decision) if decision else None,
        policy=PolicyEvalOut.model_validate(policy_eval) if policy_eval else None,
        approvals=[
            ApprovalOut.model_validate(a).model_copy(
                update={
                    "decision_code": decision.decision_code if decision else None,
                    "amount": decision.amount if decision else None,
                    "currency": decision.currency if decision else None,
                    "confidence": decision.confidence if decision else None,
                    "rationale": decision.rationale if decision else None,
                    "case_number": dispute.paypal_case_number,
                    "reason_code": dispute.reason_code,
                }
            )
            for a in approvals
        ],
        refunds=[
            RefundOut.model_validate(r).model_copy(
                update={"simulated": bool((r.raw or {}).get("simulated"))}
            )
            for r in refunds
        ],
    )


@router.post(
    "/{dispute_id}/messages",
    response_model=MessageOut,
    status_code=201,
    dependencies=[Depends(require_session)],
)
async def add_case_message(
    dispute_id: UUID, body: MessageCreate, session: SessionDep
) -> MessageOut:
    """Persist a merchant note on the complaint thread.

    This is deliberately not presented as a PayPal message: the outbound PayPal
    messaging API is not wired in this build. The note is part of the case file
    and is available to the next agent run.
    """
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == dispute_id))
    ).scalar_one_or_none()
    if dispute is None:
        raise NotFoundError(f"Dispute {dispute_id} does not exist.")
    text = body.body.strip()
    if not text:
        raise ValidationError("A merchant note cannot be empty.")
    message = DisputeMessage(
        dispute_id=dispute.id,
        direction="outbound",
        channel="case_file",
        author_type="merchant",
        body=text,
        sent_at=datetime.now(UTC),
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return MessageOut.model_validate(message)


@router.post(
    "/{dispute_id}/run",
    response_model=RunOut,
    dependencies=[Depends(require_session)],
)
async def start_run(dispute_id: UUID, session: SessionDep) -> RunOut:
    run = await run_dispute(session, dispute_id, trigger="manual")
    return RunOut.model_validate(run)
