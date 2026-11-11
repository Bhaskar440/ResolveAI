"""Run orchestration: case file -> LangGraph -> policy gate -> decision/approval -> executor."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
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
    Refund,
)
from app.services.audit import append_audit
from app.services.execution import execute_plan
from app.services.knowledge import RetrievalResult, retrieve_policy_citations

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
    order_raw = (order.raw or {}) if order else {}
    tracking = order_raw.get("tracking") or raw.get("tracking")
    shipping_raw = dict(order_raw.get("shipping") or raw.get("shipping") or {})
    if tracking:
        shipping_raw.setdefault("carrier", tracking.get("carrier"))
        shipping_raw.setdefault(
            "tracking_number", tracking.get("number") or tracking.get("tracking_number")
        )
        shipping_raw.setdefault("status", tracking.get("status"))
    if shipping_raw:
        shipping_raw["source"] = (
            "orders.raw" if order_raw.get("tracking") or order_raw.get("shipping") else "disputes.raw"
        )
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
            "status": order.status,
        }
        if order
        else None,
        "capture": {
            "paypal_capture_id": capture.paypal_capture_id,
            "seller_protection_status": capture.seller_protection_status,
            "refundable_amount": str(money(capture.amount)),
            "amount": str(money(capture.amount)),
            "currency": capture.currency,
            "status": capture.status,
        }
        if capture
        else None,
        "tracking": tracking,
        "shipping": shipping_raw or None,
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


async def _append_execution_step(
    session: AsyncSession,
    run_id: UUID | None,
    refund: Refund | None,
    plan: PaymentPlan,
    *,
    initiated_by: str,
) -> None:
    """Record the backend call and its verification result in the run trace."""
    if run_id is None or refund is None:
        return
    max_seq = (
        await session.execute(
            select(func.max(AgentStep.seq)).where(AgentStep.run_id == run_id)
        )
    ).scalar() or 0
    simulated = bool((refund.raw or {}).get("simulated"))
    verified = bool(refund.paypal_refund_id) and refund.status.upper() in {"COMPLETED", "PENDING"}
    session.add(
        AgentStep(
            run_id=run_id,
            seq=max_seq + 1,
            node="payment_backend",
            agent="payment",
            step_type="execution",
            summary=(
                f"PayPal refund {refund.status}"
                + (" (simulated replay)" if simulated else " (live sandbox)")
                + (" — verified" if verified else " — NOT verified")
            ),
            payload={
                "plan_action": plan.action,
                "plan_amount": str(plan.amount),
                "capture": plan.capture_id,
                "refund_id": refund.paypal_refund_id,
                "refund_status": refund.status,
                "simulated": simulated,
                "verified": verified,
                "initiated_by": initiated_by,
                "backend_call": "executed_by_signed_plan_executor",
            },
        )
    )


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


async def _retrieve_policies(session: AsyncSession, case: dict) -> RetrievalResult:
    try:
        return await retrieve_policy_citations(session, case)
    except Exception as exc:  # noqa: BLE001 - knowledge failure must degrade to the ask branch, not crash
        logger.warning("policy retrieval failed: %s", exc)
        return RetrievalResult(
            query="",
            mode="none",
            warning=f"Policy retrieval failed: {str(exc)[:300]}",
        )


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
    retrieval = await _retrieve_policies(session, case)
    policy_citations = [citation.model_dump(mode="json") for citation in retrieval.citations]

    run = AgentRun(
        id=uuid4(),
        dispute_id=dispute.id,
        thread_id=f"dispute:{dispute.id}:{uuid4().hex[:8]}",
        status="RUNNING",
        trigger=trigger,
        model_primary=settings.llm_model_fast or None,
        started_at=datetime.now(UTC),
        graph_version="v3",
    )
    session.add(run)
    prior_status = dispute.status
    dispute.status = "ANALYZING"
    await session.flush()

    state = {
        "run_id": str(run.id),
        "case": case,
        "policy": policy,
        "policy_citations": policy_citations,
        "policy_retrieval": retrieval.meta(),
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
    retrieval_label = (
        "pgvector cosine" if retrieval.mode == "vector" else f"{retrieval.mode} fallback"
    )
    retrieval_summary = (
        f"Retrieved {len(policy_citations)} policy clause(s) via {retrieval_label}"
        if policy_citations
        else f"No policy clause retrieved ({retrieval.mode})"
    )
    steps = [
        {
            "node": "knowledge_retrieval",
            "agent": "system",
            "step_type": "retrieval",
            "summary": retrieval_summary,
            "payload": {
                **retrieval.meta(),
                "citations": policy_citations,
            },
            "latency_ms": retrieval.latency_ms,
        },
        *steps,
    ]
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
    run.tool_calls = len(steps)
    run.output_tokens = sum(int(s.get("tokens") or 0) for s in steps)
    run.cost_usd = Decimal("0.0000")
    run.ended_at = datetime.now(UTC)

    # Missing information is a terminal, honest outcome: ask, do not guess and
    # do not move money. The case can be re-run after the buyer answers.
    if result.get("needs_information"):
        questions = result.get("requested_info") or []
        run.status = "NEEDS_INFO"
        dispute.status = "AWAITING_INFO"
        dispute.agent_summary = ("Missing information: " + "; ".join(questions))[:1000]
        await append_audit(
            session,
            merchant_id=dispute.merchant_id,
            actor_type="agent",
            action="information.requested",
            entity_type="dispute",
            entity_id=str(dispute.id),
            after={"questions": questions, "run_id": str(run.id)},
        )
        await session.commit()
        await session.refresh(run)
        return run

    final_policy = (result.get("policy") or {}).get("final") or {}
    decision_data = result.get("decision") or {}
    action = decision_data.get("action", "ESCALATE")
    amount = money(decision_data.get("amount"))
    confidence = float(decision_data.get("confidence") or 0)
    requires_approval = bool(decision_data.get("requires_approval"))
    decision_citations = decision_data.get("policy_citations") or policy_citations

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
        envelope={
            "pre": pre,
            "final": final_policy,
            "agent": {
                "reasoning": decision_data.get("reasoning"),
                "missing_evidence": decision_data.get("missing_evidence") or [],
                "rejected_alternatives": decision_data.get("rejected_alternatives") or [],
                "buyer_intake": result.get("buyer_intake"),
                "merchant_evidence": result.get("merchant_evidence"),
                "payment_preflight": result.get("payment_preflight"),
                "policy_citations": decision_citations,
                "policy_retrieval": result.get("policy_retrieval") or retrieval.meta(),
            },
        },
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
        reasoning=decision_data.get("reasoning"),
        missing_evidence=decision_data.get("missing_evidence") or [],
        policy_citations=decision_citations,
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
            refund = await execute_plan(
                session, plan=plan, dispute=dispute, decision=decision, initiated_by="agent"
            )
            await _append_execution_step(
                session, run.id, refund, plan, initiated_by="agent"
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
            refund = await execute_plan(
                session,
                plan=plan,
                dispute=dispute,
                decision=decision,
                initiated_by="human",
                actor_id=str(user_id) if user_id else None,
            )
            await _append_execution_step(
                session,
                approval.requested_by_run_id,
                refund,
                plan,
                initiated_by="human",
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
