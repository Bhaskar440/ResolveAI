from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Header, Query
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.errors import NotFoundError
from app.db.models import Approval, Decision, Dispute
from app.schemas.responses import ApprovalDecision, ApprovalOut
from app.services.orchestrator import decide_approval

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _out(approval: Approval, decision: Decision, dispute: Dispute) -> ApprovalOut:
    return ApprovalOut.model_validate(approval).model_copy(
        update={
            "decision_code": decision.decision_code,
            "amount": decision.amount,
            "currency": decision.currency,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
            "case_number": dispute.paypal_case_number,
            "reason_code": dispute.reason_code,
        }
    )


@router.get("", response_model=list[ApprovalOut])
async def list_approvals(
    session: SessionDep, status: str = Query("pending"), limit: int = Query(50, ge=1, le=200)
) -> list[ApprovalOut]:
    stmt = (
        select(Approval, Decision, Dispute)
        .join(Decision, Approval.decision_id == Decision.id)
        .join(Dispute, Approval.dispute_id == Dispute.id)
        .order_by(Approval.requested_at.asc())
        .limit(limit)
    )
    if status != "all":
        stmt = stmt.where(Approval.status == status)
    rows = (await session.execute(stmt)).all()
    return [_out(a, d, s) for a, d, s in rows]


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
async def decide(
    approval_id: UUID,
    body: ApprovalDecision,
    session: SessionDep,
    x_operator: str | None = Header(default=None, alias="X-Operator"),
) -> ApprovalOut:
    approval = await decide_approval(
        session, approval_id, approve=body.approve, note=body.note, user_id=None
    )
    decision = (
        await session.execute(select(Decision).where(Decision.id == approval.decision_id))
    ).scalar_one()
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == approval.dispute_id))
    ).scalar_one_or_none()
    if dispute is None:
        raise NotFoundError("Dispute for this approval no longer exists.")
    out = _out(approval, decision, dispute)
    return out.model_copy(update={"note": approval.note or (f"operator:{x_operator}" if x_operator else None)})
