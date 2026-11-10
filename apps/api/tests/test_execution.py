"""Executor invariants: signed plans, deterministic replay receipts, idempotency."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.nodes import make_plan
from app.core.security import sign_plan
from app.paypal.replay import ReplayAdapter


def case() -> dict:
    return {
        "dispute_id": "00000000-0000-0000-0000-000000000001",
        "paypal_dispute_id": "PP-D-TEST-1",
        "case_number": "PP-D-TEST-1",
        "reason_code": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "amount": "40.00",
        "currency": "USD",
        "capture": {"paypal_capture_id": "CAP-TEST"},
    }


def test_plan_signature_verifies_and_detects_tampering():
    plan = make_plan(case(), {"action": "REFUND_FULL", "amount": "40.00"}, "run-1")
    assert plan is not None
    assert sign_plan(plan.model_dump(mode="json", exclude={"signature"})) == plan.signature

    tampered = plan.model_copy(update={"amount": Decimal("400.00")})
    assert sign_plan(tampered.model_dump(mode="json", exclude={"signature"})) != tampered.signature


def test_plan_key_is_stable_for_the_same_case():
    a = make_plan(case(), {"action": "REFUND_FULL", "amount": "40.00"}, "run-1")
    b = make_plan(case(), {"action": "REFUND_FULL", "amount": "40.00"}, "run-2")
    assert a is not None and b is not None
    assert a.idempotency_key == b.idempotency_key


def test_no_plan_for_non_money_actions():
    assert make_plan(case(), {"action": "DEFEND", "amount": "0.00"}, "run-1") is None
    assert make_plan(case(), {"action": "ESCALATE", "amount": "0.00"}, "run-1") is None


@pytest.mark.asyncio
async def test_replay_refunds_are_simulated_and_deterministic():
    adapter = ReplayAdapter()
    first = await adapter.refund(
        "CAP-TEST", Decimal("40.00"), "USD", idempotency_key="key-1", note="demo"
    )
    second = await adapter.refund(
        "CAP-TEST", Decimal("40.00"), "USD", idempotency_key="key-1", note="demo"
    )
    other = await adapter.refund(
        "CAP-TEST", Decimal("40.00"), "USD", idempotency_key="key-2", note="demo"
    )
    assert first.simulated is True
    assert first.paypal_refund_id.startswith("REPLAY-RF-")
    assert first.paypal_refund_id == second.paypal_refund_id
    assert first.paypal_refund_id != other.paypal_refund_id
