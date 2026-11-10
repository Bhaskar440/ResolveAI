from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.errors import NotFoundError
from app.db.models import AgentMessage, AgentRun, AgentStep
from app.schemas.responses import AgentMessageOut, RunDetail, RunOut, StepOut

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[RunOut])
async def list_runs(
    session: SessionDep,
    dispute_id: UUID | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[RunOut]:
    stmt = select(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit)
    if dispute_id:
        stmt = stmt.where(AgentRun.dispute_id == dispute_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [RunOut.model_validate(r) for r in rows]


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: UUID, session: SessionDep) -> RunDetail:
    run = (
        await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError(f"Run {run_id} does not exist.")
    steps = (
        (
            await session.execute(
                select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    messages = (
        (
            await session.execute(
                select(AgentMessage)
                .where(AgentMessage.run_id == run_id)
                .order_by(AgentMessage.seq.asc())
            )
        )
        .scalars()
        .all()
    )
    return RunDetail(
        run=RunOut.model_validate(run),
        steps=[StepOut.model_validate(s) for s in steps],
        messages=[AgentMessageOut.model_validate(m) for m in messages],
    )
