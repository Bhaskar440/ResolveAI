"""Prompt 4: corpus metadata, chunking, embeddings fallback and sufficiency routing."""

from __future__ import annotations

import math

from app.agents.embeddings import HashEmbedder
from app.agents.llm import LLMResult
from app.agents.nodes import join_node
from app.agents.policy.engine import PolicyInput, evaluate
from app.agents.rag import chunk_document, load_documents
from app.services.knowledge import build_case_query


class DeadLLM:
    available = False
    provider = "none"

    async def complete_json(self, *args, **kwargs) -> LLMResult:
        return LLMResult(data=None, error="forced offline")


def _case() -> dict:
    return {
        "dispute_id": "00000000-0000-0000-0000-000000000003",
        "paypal_dispute_id": "PP-D-P4-1",
        "case_number": "PP-D-P4-1",
        "reason_code": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "reason_detail": "parcel never arrived",
        "amount": "40.00",
        "currency": "USD",
        "merchant_currency": "USD",
        "paypal_status": "OPEN",
        "lifecycle_stage": "INQUIRY",
        "hours_to_deadline": 48.0,
        "buyer_label": "Buyer #p4",
        "order": {
            "paypal_order_id": "ORDER-P4",
            "item_title": "Ceramic mug",
            "amount": "40.00",
            "currency": "USD",
            "status": "COMPLETED",
        },
        "capture": {
            "paypal_capture_id": "CAP-P4",
            "seller_protection_status": "ELIGIBLE",
            "refundable_amount": "40.00",
            "amount": "40.00",
            "currency": "USD",
            "status": "COMPLETED",
        },
        "tracking": {"carrier": "UPS", "number": "1Z-P4", "status": "IN_TRANSIT"},
        "shipping": {
            "carrier": "UPS",
            "tracking_number": "1Z-P4",
            "status": "IN_TRANSIT",
            "source": "orders.raw",
        },
        "risk_signals": [],
        "messages": [
            {"direction": "inbound", "author_type": "buyer", "body": "Parcel never arrived."}
        ],
    }


def _policy(case: dict) -> dict:
    return evaluate(
        PolicyInput(
            reason_code=case["reason_code"],
            amount=case["amount"],
            currency=case["currency"],
            confidence=0.85,
            refundable_amount=case["capture"]["refundable_amount"],
            seller_protection="ELIGIBLE",
            tracking_status="IN_TRANSIT",
            hours_to_deadline=48.0,
        )
    ).to_dict()


def test_corpus_has_all_required_categories():
    documents = load_documents()
    assert len(documents) == 5
    assert {document.category for document in documents} == {
        "refund",
        "return",
        "shipping",
        "replacement",
        "resolution",
    }
    assert all(document.title and document.source_key.endswith(".md") for document in documents)


def test_chunking_is_stable_and_source_attributed():
    document = next(doc for doc in load_documents() if doc.category == "shipping")
    chunks = chunk_document(document, max_chars=1400, overlap=0)
    assert chunks
    assert chunks[0].chunk_id == "shipping-policy:shipping-and-delivery"
    assert all(chunk.source == document.source_key for chunk in chunks)
    assert all(chunk.document == document.title for chunk in chunks)
    assert all(chunk.category == "shipping" for chunk in chunks)
    again = chunk_document(document)
    assert [chunk.chunk_id for chunk in chunks] == [chunk.chunk_id for chunk in again]


async def test_hash_embedder_is_deterministic_and_normalized():
    embedder = HashEmbedder(768)
    first = await embedder.embed_one("lost parcel refund policy")
    second = await embedder.embed_one("lost parcel refund policy")
    assert len(first) == 768
    assert first == second
    assert math.isclose(math.sqrt(sum(value * value for value in first)), 1.0, rel_tol=1e-6)


def test_build_case_query_includes_dispute_facts():
    query = build_case_query(_case())
    assert "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" in query
    assert "parcel never arrived" in query
    assert "Ceramic mug" in query
    assert "UPS" in query


async def test_insufficient_policy_evidence_routes_to_request_info(monkeypatch):
    from app.agents.graph import GRAPH

    monkeypatch.setattr("app.agents.nodes.get_llm", lambda: DeadLLM())
    monkeypatch.setattr("app.agents.nodes.retrieve_policies", lambda *a, **k: [])
    case = _case()
    state = await GRAPH.ainvoke(
        {
            "run_id": "00000000-0000-0000-0000-000000000004",
            "case": case,
            "policy": _policy(case),
            "rounds": 1,
            "steps": [],
            "messages": [],
            "errors": [],
        },
        config={"recursion_limit": 20},
    )
    assert state["needs_information"] is True
    assert any("policy" in item.lower() for item in state["requested_info"])
    assert "decision" not in state
    assert "plan" not in state


def test_join_adds_missing_policy_clause():
    state = join_node(
        {
            "case": _case(),
            "policy_citations": [],
            "missing_info": [],
            "blocking_missing_info": [],
        }
    )
    assert state["needs_information"] is True
    assert state["policy_evidence_sufficient"] is False
    assert any("policy" in item.lower() for item in state["missing_info"])
