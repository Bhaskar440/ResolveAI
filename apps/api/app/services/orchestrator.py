"""Run orchestration: case file -> LangGraph -> policy gate -> decision/approval -> executor."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import PaymentPlan
from app.agents.graph import GRAPH
from app.agents.nodes import make_plan, money
from app.agents.policy.engine import PolicyInput, evaluate, inputs_digest
from app.core.config import get_settings
from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    AgentMessage,
    AgentRun,
    AgentStep,
    Approval,
    Capture,
    Decision,
    Dispute,
    DisputeMessage,
    Merchant,
    Order,
    PolicyEvaluation,
)
from app.services.audit import append_audit
from app.services.execution import execute_plan

logger = logging.getLogger("resolveai.orchestrator")
settings = get_settings()

TERMINAL_RUN_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


async def load_case(session: AsyncSession, dispute: Dispute) -> dict:
    merchant = (
        await session.execute(select(Merchant).where(Merchant.id == dispute.merchant_id))
    ).scalar_one()
    order = (
        await session.execute(select(Order).where(Order.id == dispute.order_id))
    ).scalar_one_or_none() if dispute.order_id else None
    capture = (
        await session.execute(select(Capture).where(Capture.id == dispute.capture_id))
    ).scalar_one_or_none() if dispute.capture_id else None
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
    raw = dispute.raw or {}
    hours = None
    if dispute.response_due_by:
        delta = dispute.response_due_by - datetime.now(UTC)
        hours = round(delta.total_seconds() / 3600, 2)

    return {
        "dispute_id": str(dispute.id),
        "paypal_dispute_id": dispute.paypal_dispute_id,
        "case_number": dispute.paypal_case_number,
        "reason_code": dispute.reason_code,
        "reason_detail": dispute.reason_detail,
        "amount": str(money(dispute.amount)),
        "currency": dispute.currency,
        "merchant_currency": merchant.currency,
        "paypal_status": dispute.paypal_status,
        "lifecycle_stage": dispute.lifecycle_stage,
        "due": dispute.response_due_by.isoformat() if dispute.response_due_by else None,
        "hours_to_deadline": hours,
        "buyer_label": dispute.buyer_label,
        "order": {
            "paypal_order_id": order.paypal_order_id,
            "item_title": order.item_title,
            "amount": str(money(order.amount)),
            "currency": order.currency,
        }
        if order
        else None,
        "capture": {
            "paypal_capture_id": capture.paypal_capture_id,
            "seller_protection_status": capture.seller_protection_status,
            "refundable_amount": str(money(capture.amount)),
            "status": capture.status,
        }
        if capture
        else None,
        "tracking": raw.get("tracking"),
        "risk_signals": raw.get("risk_signals") or [],
        "messages": [
            {
                "direction": m.direction,
                "author_type": m.author_type,
                "body": m.body,
                "sent_at": m.sent_at.isoformat() if m.sent_at else None,
            }
            for m in messages
        ],
    }


def provisional_policy(case: dict) -> dict:
    """Envelope used to constrain the Resolution agent before it states a confidence."""
    result = evaluate(
        PolicyInput(
            reason_code=case["reason_code"],
            amount=case["amount"],
            currency=case["currency"],
            merchant_currency=case["merchant_currency"],
            confidence=0.85,
            refundable_amount=(case.get("capture") or {}).get("refundable_amount"),
            seller_protection=(case.get("capture") or {}).get("seller_protection_status", "UNKNOWN"),
            tracking_status=(case.get("tracking") or {}).get("status", "UNKNOWN"),
            hours_to_deadline=case.get("hours_to_deadline"),
            dispute_status=case.get("paypal_status", "OPEN"),
        )
    )
    return result.to_dict()


async def run_dispute(
    session: AsyncSession, dispute_id: UUID, *, trigger: str = "manual"
) -> AgentRun:
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == dispute_id))
    ).scalar_one_or_none()
    if dispute is None:
        raise NotFoundError(f"Dispute {dispute_id} does not exist.")
    if dispute.status in {"RESOLVED"}:
        raise ConflictError("Dispute is already resolved.")
    if dispute.status == "AWAITING_APPROVAL":
        raise ConflictError("Dispute already has a pending approval.")

    case = await load_case(session, dispute)
    policy = provisional_policy(case)

    run = AgentRun(
        id=uuid4(),
        dispute_id=dispute.id,
        thread_id=f"dispute:{dispute.id}:{uuid4().hex[:8]}",
        status="RUNNING",
        trigger=trigger,
        model_primary=settings.llm_model_fast or None,
        started_at=datetime.now(UTC),
        graph_version="v1",
    )
    session.add(run)
    prior_status = dispute.status
    dispute.status = "ANALYZING"
    await session.flush()

    state = {
        "run_id": str(run.id),
        "case": case,
        "policy": policy,
        "rounds": 1,
        "steps": [],
        "messages": [],
        "errors": [],
    }

    try:
        result = await GRAPH.ainvoke(state, config={"recursion_limit": 20})
    except Exception as exc:  # graph failure must be visible, never silent
        logger.exception("graph failed for dispute %s", dispute.paypal_dispute_id)
        run.status = "FAILED"
        run.error_code = "GRAPH_ERROR"
        run.error_detail = str(exc)[:1000]
        run.ended_at = datetime.now(UTC)
        dispute.status = prior_status
        await session.commit()
        raise

    steps = result.get("steps") or []
    messages = result.get("messages") or []
    for seq, step in enumerate(steps, start=1):
        session.add(
            AgentStep(
                run_id=run.id,
                seq=seq,
                node=step["node"],
                agent=step["agent"],
                step_type=step["step_type"],
                summary=step.get("summary"),
                payload=step.get("payload") or {},
                latency_ms=step.get("latency_ms"),
                tokens=step.get("tokens"),
            )
        )
    for seq, msg in enumerate(messages, start=1):
        session.add(
            AgentMessage(
                run_id=run.id,
                seq=seq,
                from_agent=msg["sender"],
                to_agent=msg.get("to", "resolution"),
                msg_type=msg["type"],
                claim=msg["claim"],
                evidence_refs=msg.get("evidence_refs") or [],
                confidence=Decimal(str(msg.get("confidence", 0.5))),
                constraints=msg.get("constraints") or {},
                rationale=msg.get("rationale"),
            )
        )

    run.iterations = int(result.get("rounds", 1))
    run.output_tokens = sum(int(s.get("tokens") or 0) for s in steps)
    run.cost_usd = Decimal("0.0000")
    run.ended_at = datetime.now(UTC)

    final_policy = (result.get("policy") or {}).get("final") or {}
    decision_data = result.get("decision") or {}
    action = decision_data.get("action", "ESCALATE")
    amount = money(decision_data.get("amount"))
    confidence = float(decision_data.get("confidence") or 0)
    requires_approval = bool(decision_data.get("requires_approval"))

    pre = result.get("policy") or policy
    policy_eval = PolicyEvaluation(
        dispute_id=dispute.id,
        run_id=run.id,
        ruleset_version=str(pre.get("ruleset_version", "unknown")),
        inputs_hash=inputs_digest(
            PolicyInput(
                reason_code=case["reason_code"],
                amount=case["amount"],
                currency=case["currency"],
                merchant_currency=case["merchant_currency"],
                confidence=confidence,
                refundable_amount=(case.get("capture") or {}).get("refundable_amount"),
                seller_protection=(case.get("capture") or {}).get(
                    "seller_protection_status", "UNKNOWN"
                ),
                tracking_status=(case.get("tracking") or {}).get("status", "UNKNOWN"),
                hours_to_deadline=case.get("hours_to_deadline"),
                dispute_status=case.get("paypal_status", "OPEN"),
            )
        ),
        result=str(final_policy.get("decision", "unknown")),
        matched_rules=final_policy.get("matched_rules") or [],
        envelope={"pre": pre, "final": final_policy},
    )
    session.add(policy_eval)
    await session.flush()

    decision = Decision(
        dispute_id=dispute.id,
        run_id=run.id,
        decision_code=action,
        amount=amount,
        currency=case["currency"],
        confidence=Decimal(str(round(confidence, 3))),
        rationale=decision_data.get("rationale"),
        cited_evidence=decision_data.get("evidence_refs") or [],
        policy_eval_id=policy_eval.id,
        requires_approval=requires_approval,
        status="proposed",
        decided_by="agent",
    )
    session.add(decision)
    await session.flush()

    dispute.confidence = Decimal(str(round(confidence, 3)))
    dispute.decision_code = action
    dispute.requires_approval = requires_approval
    dispute.agent_summary = (decision_data.get("rationale") or "")[:1000]

    plan_data = result.get("plan")

    if plan_data:
        plan = PaymentPlan(**plan_data)
        if requires_approval:
            approval = Approval(
                decision_id=decision.id,
                dispute_id=dispute.id,
                requested_by_run_id=run.id,
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            session.add(approval)
            decision.status = "pending_approval"
            run.status = "WAITING_APPROVAL"
            dispute.status = "AWAITING_APPROVAL"
            await append_audit(
                session,
                merchant_id=dispute.merchant_id,
                actor_type="agent",
                action="approval.requested",
                entity_type="dispute",
                entity_id=str(dispute.id),
                after={"action": action, "amount": str(amount), "approval_id": str(approval.id)},
            )
        else:
            await execute_plan(
                session, plan=plan, dispute=dispute, decision=decision, initiated_by="agent"
            )
            run.status = "COMPLETED"
            decision.status = "executed"
            await append_audit(
                session,
                merchant_id=dispute.merchant_id,
                actor_type="agent",
                action="decision.executed",
                entity_type="dispute",
                entity_id=str(dispute.id),
                after={"action": action, "amount": str(amount)},
            )
    else:
        decision.status = "recorded"
        run.status = "COMPLETED"
        dispute.status = "ESCALATED"
        await append_audit(
            session,
            merchant_id=dispute.merchant_id,
            actor_type="agent",
            action="decision.recorded",
            entity_type="dispute",
            entity_id=str(dispute.id),
            after={"action": action, "amount": str(amount)},
        )

    await session.commit()
    await session.refresh(run)
    return run


async def decide_approval(
    session: AsyncSession,
    approval_id: UUID,
    *,
    approve: bool,
    note: str | None = None,
    user_id: UUID | None = None,
) -> Approval:
    approval = (
        await session.execute(select(Approval).where(Approval.id == approval_id))
    ).scalar_one_or_none()
    if approval is None:
        raise NotFoundError(f"Approval {approval_id} does not exist.")
    if approval.status != "pending":
        raise ConflictError(f"Approval is already {approval.status}.")

    decision = (
        await session.execute(select(Decision).where(Decision.id == approval.decision_id))
    ).scalar_one()
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == approval.dispute_id))
    ).scalar_one()

    approval.status = "approved" if approve else "rejected"
    approval.resolved_at = datetime.now(UTC)
    approval.note = note
    approval.resolved_by_user_id = user_id

    if approve:
        case = await load_case(session, dispute)
        plan = make_plan(
            case,
            {"action": decision.decision_code, "amount": str(decision.amount)},
            str(approval.requested_by_run_id or ""),
        )
        if plan is None:
            dispute.status = "ESCALATED"
            decision.status = "recorded"
        else:
            await execute_plan(
                session,
                plan=plan,
                dispute=dispute,
                decision=decision,
                initiated_by="human",
                actor_id=str(user_id) if user_id else None,
            )
            decision.status = "executed"
    else:
        decision.status = "rejected"
        dispute.status = "ESCALATED"

    run = (
        await session.execute(
            select(AgentRun).where(AgentRun.id == approval.requested_by_run_id)
        )
    ).scalar_one_or_none()
    if run and run.status not in TERMINAL_RUN_STATES:
        run.status = "COMPLETED"
        run.ended_at = datetime.now(UTC)

    await append_audit(
        session,
        merchant_id=dispute.merchant_id,
        actor_type="human",
        actor_id=str(user_id) if user_id else "demo-operator",
        action="approval.approved" if approve else "approval.rejected",
        entity_type="approval",
        entity_id=str(approval.id),
        after={"note": note, "decision": decision.decision_code, "amount": str(decision.amount)},
    )
    await session.commit()
    await session.refresh(approval)
    return approval


async def latest_state(session: AsyncSession, dispute_id: UUID) -> dict:
    dispute = (
        await session.execute(select(Dispute).where(Dispute.id == dispute_id))
    ).scalar_one_or_none()
    if dispute is None:
        raise NotFoundError(f"Dispute {dispute_id} does not exist.")
    runs = (
        (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.dispute_id == dispute_id)
                .order_by(AgentRun.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .all()
    )
    return {"dispute": dispute, "run": runs[0] if runs else None}
