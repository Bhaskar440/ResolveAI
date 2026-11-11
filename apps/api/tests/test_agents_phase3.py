"""Phase 3: intake, policy RAG, structured evidence, missing info, payment preflight."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.agents.llm import LLMResult
from app.agents.nodes import buyer_intake_node
from app.agents.policy.engine import PolicyInput, evaluate
from app.agents.rag import load_policy_chunks, retrieve_policies


class DeadLLM:
    available = False
    provider = "none"

    async def complete_json(self, *args, **kwargs) -> LLMResult:
        return LLMResult(data=None, error="forced offline")


class FakeLLM:
    """Returns one scripted JSON payload; separate from the deterministic path."""

    available = True
    provider = "fake"

    def __init__(self, payload: dict):
        self.payload = payload

    async def complete_json(self, *args, **kwargs) -> LLMResult:
        return LLMResult(data=self.payload, text=json.dumps(self.payload), model="fake")


def build_case(
    reason: str = "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
    amount: str = "40.00",
    *,
    with_order: bool = True,
    with_tracking: bool = True,
    with_message: bool = True,
) -> dict:
    return {
        "dispute_id": "00000000-0000-0000-0000-000000000001",
        "paypal_dispute_id": "PP-D-TEST-1",
        "case_number": "PP-D-TEST-1",
        "reason_code": reason,
        "reason_detail": "test narrative" if with_message else None,
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
            "status": "COMPLETED",
        }
        if with_order
        else None,
        "capture": {
            "paypal_capture_id": "CAP-TEST",
            "seller_protection_status": "ELIGIBLE",
            "refundable_amount": amount,
            "amount": amount,
            "currency": "USD",
            "status": "COMPLETED",
        }
        if with_order
        else None,
        "tracking": {"carrier": "UPS", "number": "1Z-TEST", "status": "IN_TRANSIT"}
        if with_tracking
        else None,
        "shipping": {
            "carrier": "UPS",
            "tracking_number": "1Z-TEST",
            "status": "IN_TRANSIT",
            "source": "orders.raw",
        }
        if with_tracking
        else None,
        "risk_signals": [],
        "messages": [
            {"direction": "inbound", "author_type": "buyer", "body": "My parcel never arrived."}
        ]
        if with_message
        else [],
    }


def pre_policy(case: dict) -> dict:
    return evaluate(
        PolicyInput(
            reason_code=case["reason_code"],
            amount=case["amount"],
            currency=case["currency"],
            confidence=0.85,
            refundable_amount=(case.get("capture") or {}).get("refundable_amount"),
            seller_protection="ELIGIBLE",
            tracking_status=(case.get("tracking") or {}).get("status", "UNKNOWN"),
            hours_to_deadline=case["hours_to_deadline"],
        )
    ).to_dict()


async def run_graph(case: dict) -> dict:
    from app.agents.graph import GRAPH

    return await GRAPH.ainvoke(
        {
            "run_id": "00000000-0000-0000-0000-000000000002",
            "case": case,
            "policy": pre_policy(case),
            "rounds": 1,
            "steps": [],
            "messages": [],
            "errors": [],
        },
        config={"recursion_limit": 20},
    )


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr("app.agents.nodes.get_llm", lambda: DeadLLM())


def test_policy_corpus_is_loaded():
    chunks = load_policy_chunks()
    assert len(chunks) >= 5
    assert all(chunk.chunk_id for chunk in chunks)


def test_rag_retrieves_delivery_policy_for_inr():
    hits = retrieve_policies(
        "parcel never arrived no delivery scan", reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    )
    assert any(hit.chunk_id.endswith("shipping-and-delivery") for hit in hits)


def test_rag_retrieves_damage_policy_for_snad():
    hits = retrieve_policies(
        "cracked item damaged on arrival", reason_code="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED"
    )
    assert any(hit.chunk_id.endswith("damaged-or-not-as-described") for hit in hits)


def test_rag_retrieves_fraud_policy_for_unauthorised():
    hits = retrieve_policies("card was used without permission", reason_code="UNAUTHORISED")
    assert any(hit.chunk_id.endswith("unauthorised-payments-and-fraud") for hit in hits)


async def test_buyer_intake_extracts_structured_facts(offline):
    state = await buyer_intake_node({"case": build_case()})
    intake = state["buyer_intake"]
    assert intake["transaction_id"] == "ORDER-TEST"
    assert intake["reason_code"] == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED"
    assert intake["requested_resolution"] == "REFUND_FULL"
    assert intake["missing_information"] == []
    assert state["needs_information"] is False
    assert state["steps"][0]["node"] == "buyer_intake"


async def test_buyer_intake_asks_for_missing_transaction(offline):
    case = build_case(with_order=False, with_tracking=False, with_message=False)
    state = await buyer_intake_node({"case": case})
    assert state["needs_information"] is True
    assert any("transaction" in item.lower() for item in state["missing_info"])


async def test_fraud_reason_never_becomes_a_buyer_refund(offline):
    state = await buyer_intake_node({"case": build_case("UNAUTHORISED", "260.00")})
    assert state["buyer_intake"]["requested_resolution"] == "ESCALATE"
    assert Decimal(state["buyer_intake"]["requested_amount"]) == Decimal("0.00")


async def test_buyer_intake_rejects_hallucinated_transaction_id(monkeypatch):
    monkeypatch.setattr(
        "app.agents.nodes.get_llm",
        lambda: FakeLLM(
            {
                "summary": "Parcel missing",
                "transaction_id": "INVENTED-999",
                "reason_code": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
                "requested_resolution": "REFUND_FULL",
                "requested_amount": 40,
                "missing_information": [],
                "confidence": 0.9,
            }
        ),
    )
    state = await buyer_intake_node({"case": build_case()})
    assert state["buyer_intake"]["transaction_id"] == "ORDER-TEST"


async def test_graph_uses_rag_evidence_and_returns_missing_evidence(offline):
    case = build_case()
    state = await run_graph(case)
    evidence = state["merchant_evidence"]
    assert evidence["shipping"]["tracking_number"] == "1Z-TEST"
    assert evidence["policies"]
    assert all(policy["chunk_id"] for policy in evidence["policies"])
    assert any(
        ref.endswith("shipping-and-delivery") for ref in state["merchant"]["evidence_refs"]
    )
    decision = state["decision"]
    assert decision["reasoning"]
    assert decision["missing_evidence"]
    assert decision["policy_citations"]
    assert all(citation["source"] for citation in decision["policy_citations"])
    assert isinstance(decision["rejected_alternatives"], list)
    step = next(item for item in state["steps"] if item["node"] == "resolution")
    assert step["payload"]["missing_evidence"] == decision["missing_evidence"]
    assert step["payload"]["reasoning"] == decision["reasoning"]


async def test_merchant_rejects_unretrieved_policy_citation(monkeypatch):
    # The fake merchant cites a policy chunk that was never retrieved.
    monkeypatch.setattr(
        "app.agents.nodes.get_llm",
        lambda: FakeLLM(
            {
                "position": "Merchant defends",
                "proposed_action": "DEFEND",
                "amount": 0,
                "confidence": 0.8,
                "rationale": "see policy",
                "evidence_refs": ["policy:invented-clause"],
                "evidence_gaps": [],
            }
        ),
    )
    state = await run_graph(build_case())
    refs = state["merchant"]["evidence_refs"]
    assert "policy:invented-clause" not in refs
    assert any(ref.startswith("policy:") for ref in refs)


async def test_missing_information_routes_to_question_and_stops(offline):
    case = build_case(with_order=False, with_tracking=False, with_message=False)
    state = await run_graph(case)
    assert state["needs_information"] is True
    assert state["requested_info"]
    assert "decision" not in state
    assert "plan" not in state
    assert any(message["type"] == "QUESTION" for message in state["messages"])


async def test_payment_preflight_auto_and_approval_paths(offline):
    auto = await run_graph(build_case())
    assert auto["payment_preflight"]["execution_allowed"] is True
    assert auto["payment_preflight"]["requires_approval"] is False
    assert auto["plan"]["signature"]

    approval = await run_graph(
        build_case("MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED", "140.00")
    )
    assert approval["payment_preflight"]["eligible"] is True
    assert approval["payment_preflight"]["execution_allowed"] is False
    assert approval["payment_preflight"]["requires_approval"] is True

    blocked = await run_graph(build_case("UNAUTHORISED", "260.00"))
    assert blocked["payment_preflight"]["eligible"] is False
    assert blocked["plan"] is None


async def test_payment_agent_never_receives_credentials(offline):
    state = await run_graph(build_case())
    serialized = json.dumps(state, default=str).lower()
    assert "client_secret" not in serialized
    assert "access_token" not in serialized
    assert "authorization: bearer" not in serialized
    assert state["payment_preflight"]["checks"]["capture_completed"] is True
    assert Decimal(state["payment_preflight"]["refundable_after"]) == Decimal("0.00")
