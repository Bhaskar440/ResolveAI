from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api.deps import SessionDep
from app.core.errors import NotFoundError
from app.db.models import Dispute
from app.schemas.responses import DisputeList, DisputeOut

router = APIRouter(prefix="/disputes", tags=["disputes"])


@router.get("", response_model=DisputeList)
async def list_disputes(
    session: SessionDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DisputeList:
    total = (await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
    rows = (
        (
            await session.execute(
                select(Dispute)
                .order_by(Dispute.response_due_by.asc().nulls_last(), Dispute.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return DisputeList(
        items=[DisputeOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{dispute_id}", response_model=DisputeOut)
async def get_dispute(dispute_id: UUID, session: SessionDep) -> DisputeOut:
    row = (
        await session.execute(select(Dispute).where(Dispute.id == dispute_id))
    ).scalar_one_or_none()
    if row is None:
        raise NotFoundError(f"Dispute {dispute_id} does not exist.")
    return DisputeOut.model_validate(row)
