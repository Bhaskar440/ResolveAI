"""Executor — the only code path that can move money.

Preconditions it enforces itself (does not trust the caller):
  1. plan signature verifies against PLAN_SIGNING_KEY
  2. action is a money action
  3. idempotency key has not already produced a refund
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.contracts import MONEY_ACTIONS, PaymentPlan
from app.agents.nodes import money
from app.core.security import sign_plan
from app.db.models import Capture, Decision, Dispute, Refund
from app.paypal.factory import get_adapter
from app.services.audit import append_audit

logger = logging.getLogger("resolveai.execution")


class PlanIntegrityError(RuntimeError):
    pass


async def execute_plan(
    session: AsyncSession,
    *,
    plan: PaymentPlan,
    dispute: Dispute,
    decision: Decision | None = None,
    initiated_by: str = "agent",
    actor_id: str | None = None,
) -> Refund | None:
    expected = sign_plan(plan.model_dump(mode="json", exclude={"signature"}))
    if not plan.signature or expected != plan.signature:
        raise PlanIntegrityError("plan signature does not verify — refusing to execute")

    if plan.action not in MONEY_ACTIONS or plan.amount <= 0:
        return None

    existing = (
        await session.execute(
            select(Refund).where(Refund.idempotency_key == plan.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("refund already exists for key %s", plan.idempotency_key)
        return existing

    capture = (
        await session.execute(
            select(Capture).where(Capture.paypal_capture_id == plan.capture_id)
        )
    ).scalar_one_or_none()
    if capture is None:
        raise PlanIntegrityError(f"capture {plan.capture_id} is not in the database")

    adapter = get_adapter()
    receipt = await adapter.refund(
        capture.paypal_capture_id,
        plan.amount,
        plan.currency,
        idempotency_key=plan.idempotency_key,
        note=plan.note,
    )

    refund = Refund(
        merchant_id=dispute.merchant_id,
        capture_id=capture.id,
        dispute_id=dispute.id,
        paypal_refund_id=receipt.paypal_refund_id,
        amount=receipt.amount.quantize(Decimal("0.01")),
        currency=receipt.currency,
        status=receipt.status,
        reason=plan.action,
        idempotency_key=plan.idempotency_key,
        initiated_by=initiated_by,
        raw={**receipt.raw, "simulated": receipt.simulated, "mode": adapter.mode},
    )
    session.add(refund)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(Refund).where(Refund.idempotency_key == plan.idempotency_key)
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        raise

    dispute.status = "RESOLVED"
    dispute.resolved_at = datetime.now(UTC)
    dispute.recovered_amount = money(plan.amount)
    if decision is not None:
        decision.status = "executed"

    await append_audit(
        session,
        merchant_id=dispute.merchant_id,
        actor_type=initiated_by,
        actor_id=actor_id,
        action="refund.executed",
        entity_type="refund",
        entity_id=receipt.paypal_refund_id,
        after={
            "amount": str(plan.amount),
            "currency": plan.currency,
            "action": plan.action,
            "simulated": receipt.simulated,
            "capture": plan.capture_id,
        },
    )
    logger.info(
        "refund executed dispute=%s amount=%s %s simulated=%s",
        dispute.paypal_dispute_id,
        plan.amount,
        plan.currency,
        receipt.simulated,
    )
    return refund
