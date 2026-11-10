"""The graph must behave correctly with the LLM completely unavailable.

These tests force every model call to fail and assert the deterministic fallbacks
still produce a policy-compliant decision — and that the trace labels the fallback.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.llm import LLMResult
from app.agents.nodes import AgentState
from app.agents.policy.engine import PolicyInput, evaluate


class DeadLLM:
    available = False
    provider = "none"

    async def complete_json(self, *args, **kwargs) -> LLMResult:
        return LLMResult(data=None, error="forced offline")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr("app.agents.nodes.get_llm", lambda: DeadLLM())
    # the graph module imported the nodes functions, not the client, so this is enough


def build_case(reason: str, amount: str) -> dict:
    return {
        "dispute_id": "00000000-0000-0000-0000-000000000001",
        "paypal_dispute_id": "PP-D-TEST-1",
        "case_number": "PP-D-TEST-1",
        "reason_code": reason,
        "reason_detail": "test narrative",
        "amount": amount,
        "currency": "USD",
        "merchant_currency": "USD",
        "paypal_status": "OPEN",
        "lifecycle_stage": "INQUIRY",
        "due": None,
        "hours_to_deadline": 48.0,
        "buyer_label": "Buyer #test",
        "order": {
            "paypal_order_id": "ORDER-TEST",
            "item_title": "Test item",
            "amount": amount,
            "currency": "USD",
        },
        "capture": {
            "paypal_capture_id": "CAP-TEST",
            "seller_protection_status": "ELIGIBLE",
            "refundable_amount": amount,
            "status": "COMPLETED",
        },
        "tracking": None,
        "risk_signals": [],
        "messages": [],
    }


def pre_policy(case: dict) -> dict:
    return evaluate(
        PolicyInput(
            reason_code=case["reason_code"],
            amount=case["amount"],
            currency=case["currency"],
            confidence=0.85,
            refundable_amount=case["capture"]["refundable_amount"],
            seller_protection="ELIGIBLE",
            tracking_status="UNKNOWN",
            hours_to_deadline=case["hours_to_deadline"],
        )
    ).to_dict()


async def run(case: dict, rounds: int = 1) -> AgentState:
    from app.agents.graph import GRAPH

    return await GRAPH.ainvoke(
        {
            "run_id": "00000000-0000-0000-0000-000000000002",
            "case": case,
            "policy": pre_policy(case),
            "rounds": rounds,
            "steps": [],
            "messages": [],
            "errors": [],
        },
        config={"recursion_limit": 20},
    )


async def test_inr_auto_refunds_without_llm():
    case = build_case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", "40.00")
    state = await run(case)
    decision = state["decision"]
    assert decision["action"] == "REFUND_FULL"
    assert Decimal(decision["amount"]) == Decimal("40.00")
    assert decision["requires_approval"] is False
    assert state["plan"] is not None
    assert state["plan"]["action"] == "REFUND_FULL"
    assert state["plan"]["signature"]
    assert any(s["step_type"] == "fallback" for s in state["steps"])


async def test_snad_partial_offer_requires_approval_without_llm():
    case = build_case("MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED", "140.00")
    state = await run(case)
    decision = state["decision"]
    assert decision["action"] == "OFFER_PARTIAL"
    assert Decimal(decision["amount"]) == Decimal("56.00")
    # policy envelope: 140 > auto cap and confidence below auto-approve
    assert decision["requires_approval"] is True
    assert state["plan"] is not None


async def test_unauthorised_is_never_auto_paid_without_llm():
    case = build_case("UNAUTHORISED", "260.00")
    state = await run(case)
    decision = state["decision"]
    assert decision["action"] == "ESCALATE"
    assert Decimal(decision["amount"]) == Decimal("0.00")
    assert decision["requires_approval"] is True
    assert state["plan"] is None
    # fraud reasons are never auto-paid: policy either denies or demands a human
    assert state["policy"]["final"]["decision"] in {"deny", "require_approval"}
    assert Decimal(state["policy"]["final"]["max_auto_amount"]) == Decimal("0.00")


async def test_hard_cap_blocks_autonomous_refund():
    case = build_case("MERCHANDISE_OR_SERVICE_NOT_RECEIVED", "400.00")
    state = await run(case)
    decision = state["decision"]
    assert decision["requires_approval"] is True
    # the gate must not let a plan exceed the hard cap
    if state["plan"] is not None:
        assert Decimal(state["plan"]["amount"]) <= Decimal("250.00")
