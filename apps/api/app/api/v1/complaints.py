"""Complaint inbox: disputes joined with their latest buyer/merchant message."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from app.api.deps import SessionDep
from app.db.models import Dispute, DisputeMessage
from app.schemas.responses import ComplaintList, ComplaintOut

router = APIRouter(prefix="/complaints", tags=["complaints"])


@router.get("", response_model=ComplaintList)
async def list_complaints(
    session: SessionDep,
    q: str | None = Query(None, description="case / buyer / reason / narrative search"),
    status: str | None = Query(None, description="comma-separated statuses"),
    reason: str | None = None,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ComplaintList:
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
                Dispute.reason_detail.ilike(like),
            )
        )
    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = (await session.execute(count_stmt)).scalar_one()
    disputes = (
        (
            await session.execute(
                stmt.order_by(Dispute.response_due_by.asc().nulls_last(), Dispute.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    messages_by_dispute: dict = defaultdict(list)
    if disputes:
        ids = [d.id for d in disputes]
        rows = (
            (
                await session.execute(
                    select(DisputeMessage)
                    .where(DisputeMessage.dispute_id.in_(ids))
                    .order_by(
                        DisputeMessage.sent_at.asc().nulls_last(),
                        DisputeMessage.created_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        for message in rows:
            messages_by_dispute[message.dispute_id].append(message)

    items = []
    for dispute in disputes:
        messages = messages_by_dispute.get(dispute.id, [])
        latest = messages[-1] if messages else None
        items.append(
            ComplaintOut(
                dispute_id=dispute.id,
                paypal_case_number=dispute.paypal_case_number,
                paypal_dispute_id=dispute.paypal_dispute_id,
                buyer_label=dispute.buyer_label,
                reason_code=dispute.reason_code,
                reason_detail=dispute.reason_detail,
                status=dispute.status,
                amount=dispute.amount,
                currency=dispute.currency,
                response_due_by=dispute.response_due_by,
                created_at=dispute.created_at,
                message_count=len(messages),
                last_message=latest.body if latest else None,
                last_message_at=(latest.sent_at or latest.created_at) if latest else None,
                last_message_direction=latest.direction if latest else None,
            )
        )
    return ComplaintList(items=items, total=total, limit=limit, offset=offset)
