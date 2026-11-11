"""The four agents as LangGraph nodes.

All of them are pure-ish: read `state`, return a partial update. The only side
effect is an LLM HTTP call, and every LLM path has a deterministic fallback that
is labelled as such in the run trace.
"""

from __future__ import annotations

import json
import logging
import operator
from decimal import Decimal
from typing import Annotated, Any, TypedDict

from app.agents.contracts import (
    MONEY_ACTIONS,
    AgentDecision,
    AgentEnvelope,
    BuyerIntake,
    MerchantEvidence,
    PaymentPlan,
    PaymentPreflight,
    PolicyCitation,
    RequestedAction,
)
from app.agents.llm import get_llm
from app.agents.policy.engine import PolicyInput, evaluate
from app.agents.rag import retrieve_policies
from app.core.config import get_settings
from app.core.security import sign_plan

logger = logging.getLogger("resolveai.agents")
CENT = Decimal("0.01")


class AgentState(TypedDict, total=False):
    run_id: str
    case: dict[str, Any]
    policy: dict[str, Any]
    buyer_intake: dict[str, Any]
    buyer: dict[str, Any]
    merchant: dict[str, Any]
    merchant_evidence: dict[str, Any]
    policy_citations: list[dict[str, Any]]
    policy_retrieval: dict[str, Any]
    decision: dict[str, Any]
    payment_preflight: dict[str, Any]
    plan: dict[str, Any] | None
    steps: Annotated[list[dict], operator.add]
    messages: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    rounds: int
    needs_counter: bool
    counter_context: str
    missing_info: list[str]
    blocking_missing_info: list[str]
    needs_information: bool
    policy_evidence_sufficient: bool
    requested_info: list[str]


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(CENT)
    except Exception:
        return Decimal("0.00")


def _step(
    node: str,
    agent: str,
    step_type: str,
    summary: str,
    payload: dict,
    *,
    latency_ms: int = 0,
    tokens: int = 0,
    model: str | None = None,
    error: str | None = None,
) -> dict:
    return {
        "node": node,
        "agent": agent,
        "step_type": step_type,
        "summary": summary,
        "payload": payload,
        "latency_ms": latency_ms,
        "tokens": tokens,
        "model": model,
        "error": error,
    }


def _env(
    sender: str,
    msg_type: str,
    claim: str,
    evidence: list[str],
    confidence: float,
    action: str | None = None,
    amount: Decimal | None = None,
    currency: str = "USD",
    rationale: str = "",
    constraints: dict | None = None,
) -> dict:
    env = AgentEnvelope(
        sender=sender,  # type: ignore[arg-type]
        type=msg_type,  # type: ignore[arg-type]
        claim=claim,
        evidence_refs=evidence,
        confidence=max(0.0, min(1.0, float(confidence))),
        constraints=constraints or {},
        requested_action=RequestedAction(
            action=action, amount=amount, currency=currency  # type: ignore[arg-type]
        )
        if action
        else None,
        rationale=rationale[:2000],
    )
    return env.model_dump(mode="json")


def case_evidence(case: dict) -> list[str]:
    refs = [f"paypal:dispute:{case.get('paypal_dispute_id')}"]
    if case.get("order"):
        refs.append(f"paypal:order:{case['order'].get('paypal_order_id')}")
    if case.get("capture"):
        refs.append(f"paypal:capture:{case['capture'].get('paypal_capture_id')}")
    if case.get("tracking"):
        refs.append(f"tracking:{case['tracking'].get('carrier')}:{case['tracking'].get('status')}")
    refs.extend(f"message:{i}" for i in range(len(case.get("messages") or [])))
    return refs


INTAKE_SYSTEM = """You are the BUYER intake agent in a PayPal dispute. Read the buyer's messages and
transaction facts. Extract, without inventing anything:
- a one-line summary of the complaint,
- the transaction/order id if present,
- the PayPal reason code (use the supplied one unless the messages clearly contradict it),
- the resolution the buyer actually asks for,
- any information the buyer must still supply before a decision can be made.
Return strict JSON: {"summary": str, "transaction_id": str|null, "reason_code": str,
"requested_resolution": "REFUND_FULL"|"REFUND_PARTIAL"|"REPLACEMENT"|"ESCALATE"|"UNKNOWN",
"requested_amount": number|null, "missing_information": [str], "confidence": number 0..1}."""

BUYER_SYSTEM = """You are the BUYER agent in a PayPal dispute. Argue for the buyer's legitimate
remedy using ONLY the facts and the intake record provided. Never invent tracking, messages or
policy. Return strict JSON: {"claim": str, "desired_action":
"REFUND_FULL"|"REFUND_PARTIAL"|"ESCALATE", "amount": number|null,
"confidence": number 0..1, "rationale": str, "evidence_refs": [str]}."""

MERCHANT_SYSTEM = """You are the MERCHANT agent defending a seller in a PayPal dispute. Use ONLY the
order, shipping, capture and retrieved policy clauses provided. Never invent a tracking number,
delivery scan or policy clause. Minimise unjustified loss while keeping the customer; concede when
the evidence is against you. Cite policy chunks as "policy:<chunk_id>".
Return strict JSON: {"position": str, "proposed_action":
"REFUND_FULL"|"REFUND_PARTIAL"|"OFFER_PARTIAL"|"DEFEND"|"ESCALATE", "amount": number,
"confidence": number 0..1, "rationale": str, "evidence_refs": [str],
"evidence_gaps": [str]}."""

RESOLUTION_SYSTEM = """You are the RESOLUTION agent: a neutral adjudicator. Pick exactly ONE action
from allowed_actions. Never exceed max_amount. Partial/offer amounts must sit inside
partial_band [low, high]. Confidence must reflect evidence quality, not optimism.
Evaluate both sides, name what evidence is missing, and explain the choice.
Return strict JSON: {"action": str, "amount": number, "confidence": number 0..1,
"rationale": str, "reasoning": str, "evidence_refs": [str],
"missing_evidence": [str], "rejected_alternatives": [{"action": str, "reason": str}],
"needs_counter": boolean}."""


def _projection(case: dict, role: str) -> dict:
    base = {
        "reason_code": case.get("reason_code"),
        "reason_detail": case.get("reason_detail"),
        "amount": case.get("amount"),
        "currency": case.get("currency"),
        "order": case.get("order"),
        "shipping": case.get("shipping"),
        "messages": case.get("messages"),
    }
    if role == "buyer":
        base["tracking"] = case.get("tracking")
    elif role == "merchant":
        base["tracking"] = case.get("tracking")
        base["capture"] = case.get("capture")
        base["seller_protection"] = (case.get("capture") or {}).get("seller_protection_status")
        base["buyer_label"] = case.get("buyer_label")
    else:
        base.update(
            {
                "tracking": case.get("tracking"),
                "capture": case.get("capture"),
                "risk_signals": case.get("risk_signals"),
                "buyer_label": case.get("buyer_label"),
            }
        )
    return base


def _sanitize_refs(
    refs: list[str] | None, allowed: set[str], fallback: list[str]
) -> list[str]:
    """Reject hallucinated evidence ids; keep only refs that resolve in this case."""
    clean: list[str] = []
    for ref in _as_list(refs):
        value = str(ref)[:160]
        if value in allowed and value not in clean:
            clean.append(value)
    return clean or list(fallback)


def _as_list(value: Any) -> list:
    """LLMs occasionally return a string where the schema asks for a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _policy_citations_from_state(state: AgentState) -> list[PolicyCitation]:
    citations: list[PolicyCitation] = []
    for item in state.get("policy_citations") or []:
        try:
            citations.append(PolicyCitation(**item))
        except Exception:  # noqa: BLE001 - malformed state must not crash adjudication
            logger.warning("discarding malformed policy citation from state")
    return citations


def _inbound_text(case: dict) -> str:
    return " ".join(
        str(m.get("body") or "")
        for m in case.get("messages") or []
        if str(m.get("direction")) == "inbound"
    ).lower()


def _infer_buyer_request(case: dict) -> tuple[str, Decimal | None]:
    text = _inbound_text(case)
    amount = money(case.get("amount"))
    if any(word in text for word in ("partial", "half", "50 dollars", "50.00")):
        return "REFUND_PARTIAL", None
    if any(word in text for word in ("replacement", "replace it", "exchange")):
        return "REPLACEMENT", None
    if any(word in text for word in ("did not make", "unauthor", "fraud", "not mine")):
        return "ESCALATE", Decimal("0.00")
    if any(word in text for word in ("refund", "money back", "return my money")):
        return "REFUND_FULL", amount
    fallback = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": ("REFUND_FULL", amount),
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": ("REFUND_FULL", amount),
        "UNAUTHORISED": ("ESCALATE", Decimal("0.00")),
        "DUPLICATE_TRANSACTION": ("ESCALATE", Decimal("0.00")),
    }.get(str(case.get("reason_code")), ("UNKNOWN", None))
    return fallback  # type: ignore[return-value]


def _missing_buyer_info(case: dict, transaction_id: str | None, requested: str) -> list[str]:
    missing: list[str] = []
    if not transaction_id:
        missing.append("PayPal transaction or order id")
    if not _inbound_text(case) and not case.get("reason_detail"):
        missing.append("the buyer's description of what went wrong")
    if not case.get("order") and not case.get("capture"):
        missing.append("order or capture details")
    if requested == "UNKNOWN":
        missing.append("the resolution the buyer wants (refund, replacement, or escalation)")
    return missing


async def buyer_intake_node(state: AgentState) -> dict:
    """Buyer Agent, part 1: turn the complaint into structured facts + information gaps."""
    case = state["case"]
    llm = get_llm()
    context = {
        "case": _projection(case, "buyer"),
        "supplied_reason_code": case.get("reason_code"),
    }
    result = await llm.complete_json(
        INTAKE_SYSTEM,
        json.dumps(context, default=str)[:6000],
        max_tokens=300,
    )
    data = result.data or {}

    order = case.get("order") or {}
    capture = case.get("capture") or {}
    known_transaction_ids = {
        str(v)
        for v in (order.get("paypal_order_id"), capture.get("paypal_capture_id"))
        if v
    }
    deterministic_request, deterministic_amount = _infer_buyer_request(case)

    transaction_id = data.get("transaction_id")
    transaction_id = str(transaction_id) if transaction_id else None
    if transaction_id not in known_transaction_ids:
        transaction_id = (
            str(order.get("paypal_order_id")) if order.get("paypal_order_id") else None
        )
    requested = data.get("requested_resolution")
    if requested not in {"REFUND_FULL", "REFUND_PARTIAL", "REPLACEMENT", "ESCALATE", "UNKNOWN"}:
        requested = deterministic_request
    # Fraud reasons are never a buyer-requested refund in this workflow; the
    # only safe next step is PayPal's fraud review.
    if case.get("reason_code") in {"UNAUTHORISED", "DUPLICATE_TRANSACTION"}:
        requested = "ESCALATE"
    requested_amount = data.get("requested_amount")
    requested_amount = (
        money(requested_amount) if requested_amount is not None else deterministic_amount
    )
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.85 if transaction_id and _inbound_text(case) else 0.55

    missing = [str(x)[:120] for x in _as_list(data.get("missing_information")) if str(x).strip()]
    deterministic_missing = _missing_buyer_info(case, transaction_id, str(requested))
    missing = list(dict.fromkeys([*deterministic_missing, *missing]))[:6]
    # Only structural gaps block adjudication. Optional evidence (photos, etc.)
    # is reported by Resolution as missing_evidence, not used to stall the run.
    blocking = bool(deterministic_missing)

    intake = BuyerIntake(
        summary=str(
            data.get("summary") or case.get("reason_detail") or "Buyer dispute"
        )[:800],
        transaction_id=transaction_id,
        reason_code=str(case.get("reason_code") or data.get("reason_code") or "UNKNOWN"),
        requested_resolution=requested,  # type: ignore[arg-type]
        requested_amount=requested_amount if requested != "ESCALATE" else Decimal("0.00"),
        missing_information=missing,
        confidence=max(0.0, min(1.0, float(confidence))),
        evidence_refs=case_evidence(case),
        source="llm" if result.data else "deterministic",
    )
    envelope = _env(
        "buyer",
        "FINDING",
        intake.summary,
        intake.evidence_refs,
        intake.confidence,
        constraints={
            "transaction_id": intake.transaction_id,
            "requested_resolution": intake.requested_resolution,
            "missing_information": intake.missing_information,
        },
        rationale=str(data.get("rationale") or "Structured intake from the buyer's messages."),
    )
    return {
        "buyer_intake": intake.model_dump(mode="json"),
        "missing_info": intake.missing_information,
        "blocking_missing_info": deterministic_missing,
        "needs_information": blocking,
        "messages": [envelope],
        "steps": [
            _step(
                "buyer_intake",
                "buyer",
                "llm" if result.data else "fallback",
                "Buyer intake: "
                + (
                    f"{intake.requested_resolution} for {intake.transaction_id}"
                    if intake.transaction_id
                    else "transaction id missing"
                ),
                {
                    "intake": intake.model_dump(mode="json"),
                    "missing_information": intake.missing_information,
                },
                latency_ms=result.latency_ms,
                tokens=result.tokens_in + result.tokens_out,
                model=result.model,
                error=result.error,
            )
        ],
        "errors": [f"buyer intake llm: {result.error}"] if result.error else [],
    }


async def request_info_node(state: AgentState) -> dict:
    """Ask for the missing information instead of guessing or moving money."""
    case = state["case"]
    questions = list(state.get("missing_info") or ["buyer's description of the problem"])
    envelope = _env(
        "buyer",
        "QUESTION",
        "Information needed before adjudication: " + "; ".join(questions),
        case_evidence(case),
        0.5,
        constraints={"questions": questions},
        rationale="The case file is incomplete; no financial action may be taken.",
    )
    return {
        "needs_information": True,
        "requested_info": questions,
        "messages": [envelope],
        "steps": [
            _step(
                "request_info",
                "buyer",
                "question",
                "Requested missing information",
                {"questions": questions},
            )
        ],
    }


def join_node(state: AgentState) -> dict:
    """Join point: wait for both advocates, then decide whether to ask or adjudicate.

    Prompt 4 requires an explicit insufficient-evidence branch: no retrieved
    policy clause or no verified transaction record means the case is asked for
    information instead of being decided on invented facts.
    """
    case = state["case"]
    blocking = list(state.get("blocking_missing_info") or [])
    if state.get("needs_information") and not blocking:
        blocking = list(state.get("missing_info") or [])
    if not (case.get("order") or case.get("capture")):
        blocking.append("verified order or capture record")
    if not case.get("reason_code") or case.get("reason_code") == "UNKNOWN":
        blocking.append("a valid PayPal dispute reason code")
    citations = state.get("policy_citations") or []
    if not citations:
        blocking.append("applicable merchant policy clause (knowledge retrieval returned none)")
    blocking = list(dict.fromkeys(blocking))[:8]
    return {
        "needs_information": bool(blocking),
        "missing_info": blocking,
        "policy_evidence_sufficient": bool(citations),
    }


def route_after_join(state: AgentState) -> str:
    return "request_info" if state.get("needs_information") else "resolution"


async def buyer_node(state: AgentState) -> dict:
    """Buyer Agent, part 2: argue for the remedy anchored to the structured intake."""
    case = state["case"]
    intake = state.get("buyer_intake") or {}
    llm = get_llm()
    context = {
        "case": _projection(case, "buyer"),
        "intake": intake,
    }
    result = await llm.complete_json(
        BUYER_SYSTEM,
        json.dumps(context, default=str)[:7000],
        max_tokens=350,
    )
    data = result.data or {}
    allowed = {"REFUND_FULL", "REFUND_PARTIAL", "ESCALATE"}
    intake_action = {
        "REFUND_FULL": "REFUND_FULL",
        "REFUND_PARTIAL": "REFUND_PARTIAL",
        "REPLACEMENT": "REFUND_PARTIAL",
        "ESCALATE": "ESCALATE",
    }.get(str(intake.get("requested_resolution")), None)
    fallback_action = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "REFUND_FULL",
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "REFUND_FULL",
        "UNAUTHORISED": "ESCALATE",
    }.get(case["reason_code"], "REFUND_PARTIAL")
    action = data.get("desired_action")
    if action not in allowed:
        action = intake_action or fallback_action
    if case.get("reason_code") in {"UNAUTHORISED", "DUPLICATE_TRANSACTION"}:
        action = "ESCALATE"
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = {"REFUND_FULL": 0.86, "REFUND_PARTIAL": 0.7, "ESCALATE": 0.6}[action]
    claim = (
        str(data.get("claim") or intake.get("summary") or case.get("reason_detail"))[:800]
        or "Buyer requests a remedy."
    )
    amount: Decimal | None = None
    if action == "REFUND_FULL":
        amount = money(case["amount"])
    elif action == "REFUND_PARTIAL":
        amount = money(data.get("amount")) or money(intake.get("requested_amount"))
    envelope = _env(
        "buyer",
        "PROPOSAL" if action != "ESCALATE" else "FINDING",
        claim,
        _sanitize_refs(data.get("evidence_refs"), set(case_evidence(case)), case_evidence(case)),
        confidence,
        action,
        amount,
        case["currency"],
        str(data.get("rationale") or "Buyer statement and order facts."),
        {
            "max_amount": case["amount"],
            "transaction_id": intake.get("transaction_id"),
            "requested_resolution": intake.get("requested_resolution"),
        },
    )
    summary = f"Buyer asks for {action}" + ("" if result.data else " (deterministic fallback)")
    return {
        "buyer": envelope,
        "messages": [envelope],
        "steps": [
            _step(
                "buyer",
                "buyer",
                "llm" if result.data else "fallback",
                summary,
                {
                    "action": action,
                    "amount": str(amount) if amount else None,
                    "confidence": envelope["confidence"],
                    "intake_action": intake.get("requested_resolution"),
                },
                latency_ms=result.latency_ms,
                tokens=result.tokens_in + result.tokens_out,
                model=result.model,
                error=result.error,
            )
        ],
        "errors": [f"buyer llm: {result.error}"] if result.error else [],
    }


async def merchant_node(state: AgentState) -> dict:
    """Merchant Agent: PostgreSQL order/shipping facts + retrieved policy clauses."""
    case = state["case"]
    llm = get_llm()
    reason = str(case.get("reason_code") or "UNKNOWN")
    item_title = str((case.get("order") or {}).get("item_title") or "")
    query = " ".join(
        [
            reason,
            str(case.get("reason_detail") or ""),
            item_title,
            str(case.get("currency") or ""),
        ]
    )
    policies = _policy_citations_from_state(state)
    retrieval_meta = dict(state.get("policy_retrieval") or {})
    if not policies:
        policies = retrieve_policies(query, reason_code=reason, k=3)
        retrieval_meta = {
            "mode": "local-lexical",
            "embedding_model": "",
            "used_fallback": True,
            "warning": "No prefetched policy citations; merchant used local lexical retrieval.",
            "citation_ids": [citation.chunk_id for citation in policies],
        }
    policy_refs = [f"policy:{citation.chunk_id}" for citation in policies]

    tracking = case.get("tracking") or {}
    shipping = case.get("shipping") or {}
    capture = case.get("capture") or {}
    seller_protection = str(capture.get("seller_protection_status") or "UNKNOWN")

    evidence_gaps: list[str] = []
    if not tracking and not shipping.get("tracking_number"):
        evidence_gaps.append("carrier tracking number")
    if tracking and tracking.get("status") not in {"DELIVERED", "IN_TRANSIT", "ACCEPTED"}:
        evidence_gaps.append("carrier acceptance or delivery scan")
    if not capture:
        evidence_gaps.append("capture record")
    if not policies:
        evidence_gaps.append("applicable merchant policy")
    inbound = _inbound_text(case)
    if reason == "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED" and not any(
        word in inbound for word in ("photo", "picture", "image")
    ):
        evidence_gaps.append("buyer photos of the damage or defect")
    if reason in {"UNAUTHORISED", "DUPLICATE_TRANSACTION"}:
        evidence_gaps.append("device, login and account-history evidence for fraud review")

    context = {
        "case": _projection(case, "merchant"),
        "retrieved_policies": [citation.model_dump(mode="json") for citation in policies],
        "policy_citation_format": "policy:<chunk_id>",
    }
    result = await llm.complete_json(
        MERCHANT_SYSTEM,
        json.dumps(context, default=str)[:8000],
        max_tokens=400,
    )
    data = result.data or {}
    fallback = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "REFUND_FULL"
        if tracking.get("status") != "DELIVERED"
        else "DEFEND",
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "OFFER_PARTIAL",
        "UNAUTHORISED": "DEFEND",
    }.get(reason, "DEFEND")
    action = data.get("proposed_action")
    if action not in {"REFUND_FULL", "REFUND_PARTIAL", "OFFER_PARTIAL", "DEFEND", "ESCALATE"}:
        action = fallback
    amount = money(data.get("amount")) if data.get("amount") is not None else None
    if action == "OFFER_PARTIAL" and not amount:
        amount = money(Decimal(str(case["amount"])) * Decimal("0.40"))
    if action == "REFUND_FULL":
        amount = money(case["amount"])
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = 0.82 if action in {"REFUND_FULL", "DEFEND"} else 0.68
    llm_gaps = [str(gap)[:160] for gap in (data.get("evidence_gaps") or []) if str(gap).strip()]
    all_gaps = list(dict.fromkeys([*evidence_gaps, *llm_gaps]))[:8]
    allowed_refs = set(case_evidence(case)) | set(policy_refs)
    evidence_refs = _sanitize_refs(
        data.get("evidence_refs"), allowed_refs, [*case_evidence(case), *policy_refs]
    )

    evidence = MerchantEvidence(
        order=case.get("order") or {},
        shipping={**shipping, **({"tracking": tracking} if tracking else {})},
        capture=capture,
        seller_protection=seller_protection,
        policies=policies,
        evidence_gaps=all_gaps,
        source="llm" if result.data else "deterministic",
    )
    envelope = _env(
        "merchant",
        "PROPOSAL" if action != "ESCALATE" else "FINDING",
        str(data.get("position") or f"Merchant proposes {action}")[:800],
        evidence_refs,
        confidence,
        action,
        amount,
        case["currency"],
        str(data.get("rationale") or "Merchant record and seller protection facts."),
        {
            "max_offer": case["amount"],
            "policy_refs": policy_refs,
            "evidence_gaps": all_gaps,
        },
    )
    summary = f"Merchant proposes {action}" + ("" if result.data else " (deterministic fallback)")
    return {
        "merchant": envelope,
        "merchant_evidence": evidence.model_dump(mode="json"),
        "policy_citations": [citation.model_dump(mode="json") for citation in policies],
        "policy_retrieval": retrieval_meta,
        "messages": [envelope],
        "steps": [
            _step(
                "merchant",
                "merchant",
                "llm" if result.data else "fallback",
                summary,
                {
                    "action": action,
                    "amount": str(amount) if amount else None,
                    "policy_refs": policy_refs,
                    "policy_retrieval": retrieval_meta,
                    "evidence_gaps": all_gaps,
                    "evidence": evidence.model_dump(mode="json"),
                },
                latency_ms=result.latency_ms,
                tokens=result.tokens_in + result.tokens_out,
                model=result.model,
                error=result.error,
            )
        ],
        "errors": [f"merchant llm: {result.error}"] if result.error else [],
    }


def _clamp_decision(
    action: str, amount: Decimal, confidence: float, policy: dict
) -> tuple[str, Decimal]:
    allowed = policy.get("allowed_actions") or []
    if action not in allowed:
        action = "ESCALATE" if "ESCALATE" in allowed else (allowed[0] if allowed else "ESCALATE")
    if action in MONEY_ACTIONS:
        ceiling = money(policy.get("max_amount"))
        amount = min(amount, ceiling)
        band = policy.get("partial_band")
        if action in {"REFUND_PARTIAL", "OFFER_PARTIAL"} and band:
            low, high = money(band[0]), money(band[1])
            amount = max(low, min(amount, high))
        if action == "REFUND_FULL":
            amount = ceiling
        if amount <= Decimal("0.00"):
            action = "ESCALATE"
            amount = Decimal("0.00")
    else:
        amount = Decimal("0.00")
    return action, amount


async def resolution_node(state: AgentState) -> dict:
    case = state["case"]
    policy = state["policy"]
    llm = get_llm()
    merchant_evidence = state.get("merchant_evidence") or {}
    policy_citations = _policy_citations_from_state(state)
    if not policy_citations:
        for item in merchant_evidence.get("policies") or []:
            try:
                policy_citations.append(PolicyCitation(**item))
            except (TypeError, ValueError):  # tolerate legacy/partial evidence
                continue
    policy_payload = [citation.model_dump(mode="json") for citation in policy_citations]
    context = {
        "case": _projection(case, "resolution"),
        "buyer_intake": state.get("buyer_intake"),
        "buyer": state.get("buyer"),
        "merchant": state.get("merchant"),
        "merchant_evidence": {
            "order": merchant_evidence.get("order"),
            "shipping": merchant_evidence.get("shipping"),
            "capture": merchant_evidence.get("capture"),
            "seller_protection": merchant_evidence.get("seller_protection"),
            "policies": policy_payload,
            "evidence_gaps": merchant_evidence.get("evidence_gaps"),
        },
        "policy": {
            "allowed_actions": policy.get("allowed_actions"),
            "max_amount": policy.get("max_amount"),
            "partial_band": policy.get("partial_band"),
            "confidence_band": policy.get("confidence_band"),
        },
        "counter_context": state.get("counter_context") or None,
    }
    result = await llm.complete_json(
        RESOLUTION_SYSTEM,
        json.dumps(context, default=str)[:9000],
        max_tokens=500,
    )
    data = result.data or {}
    reason = case["reason_code"]

    fallback_action = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "REFUND_FULL",
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "OFFER_PARTIAL",
        "UNAUTHORISED": "ESCALATE",
    }.get(reason, "ESCALATE")
    fallback_confidence = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": 0.90,
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": 0.72,
        "UNAUTHORISED": 0.62,
    }.get(reason, 0.58)
    fallback_amount = (
        money(Decimal(str(case["amount"])) * Decimal("0.40"))
        if fallback_action == "OFFER_PARTIAL"
        else money(case["amount"])
    )

    action = data.get("action") if isinstance(data.get("action"), str) else fallback_action
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = fallback_confidence
    amount = money(data.get("amount")) if data.get("amount") is not None else fallback_amount
    action, amount = _clamp_decision(action, amount, float(confidence), policy)

    missing_evidence: list[str] = []
    for gap in merchant_evidence.get("evidence_gaps") or []:
        if gap:
            missing_evidence.append(str(gap)[:160])
    if not _inbound_text(case):
        missing_evidence.append("the buyer's written statement")
    if not (case.get("tracking") or case.get("shipping")):
        missing_evidence.append("carrier tracking or proof of delivery")
    if reason == "MERCHANDISE_OR_SERVICE_NOT_RECEIVED" and (
        (case.get("tracking") or {}).get("status") != "DELIVERED"
    ) and not any(
        "scan" in item.lower() or "tracking" in item.lower() for item in missing_evidence
    ):
        missing_evidence.append("carrier delivery scan / proof of delivery")
    if reason in {"UNAUTHORISED", "DUPLICATE_TRANSACTION"}:
        missing_evidence.append("PayPal fraud-review outcome")
    if not policy_citations:
        missing_evidence.append("applicable merchant refund policy")
    for item in data.get("missing_evidence") or []:
        if str(item).strip():
            missing_evidence.append(str(item)[:160])
    missing_evidence = list(dict.fromkeys(missing_evidence))[:8]

    rejected: list[dict] = []
    for item in data.get("rejected_alternatives") or []:
        if isinstance(item, dict) and item.get("action"):
            rejected.append(
                {
                    "action": str(item.get("action"))[:40],
                    "reason": str(item.get("reason") or "")[:240],
                }
            )
    if not rejected:
        if action == "REFUND_FULL":
            rejected = [
                {
                    "action": "DEFEND",
                    "reason": "The record shows no carrier delivery scan, so a defence is not defensible.",
                }
            ]
        elif action == "OFFER_PARTIAL":
            rejected = [
                {
                    "action": "REFUND_FULL",
                    "reason": "Full refund requires return or photographic proof that return is impractical.",
                },
                {
                    "action": "DEFEND",
                    "reason": "Damage was reported; ignoring it would breach the merchant policy.",
                },
            ]
        elif action == "ESCALATE":
            rejected = [
                {
                    "action": "REFUND_FULL",
                    "reason": "This reason code requires PayPal fraud review; autonomous money movement is blocked.",
                }
            ]

    policy_refs = [
        f"policy:{citation.chunk_id}" for citation in policy_citations
    ]
    allowed_refs = set(case_evidence(case)) | set(policy_refs)
    if data.get("rationale"):
        rationale = str(data["rationale"])[:2000]
    else:
        policy_hint = (
            f"{policy_citations[0].document} :: {policy_citations[0].section}"
            if policy_citations
            else "no retrieved policy clause"
        )
        capture_hint = (case.get("capture") or {}).get("paypal_capture_id") or "no capture"
        rationale = (
            f"Deterministic adjudication for {reason}: {action} based on capture {capture_hint} "
            f"and the retrieved policy section '{policy_hint}'. "
            f"Missing evidence: {', '.join(missing_evidence) if missing_evidence else 'none'}."
        )[:2000]
    decision = AgentDecision(
        action=action,  # type: ignore[arg-type]
        amount=amount,
        currency=case["currency"],
        confidence=max(0.0, min(1.0, float(confidence))),
        rationale=rationale,
        reasoning=str(data.get("reasoning") or rationale)[:2000],
        evidence_refs=_sanitize_refs(
            data.get("evidence_refs"), allowed_refs, [*case_evidence(case), *policy_refs]
        ),
        missing_evidence=missing_evidence,
        rejected_alternatives=rejected,
        policy_citations=policy_citations,
        policy_notes=[
            r.get("id") if isinstance(r, dict) else str(r)
            for r in (policy.get("matched_rules") or [])
        ],
    )
    envelope = _env(
        "resolution",
        "DECISION",
        f"Decision: {action} {amount} {case['currency']}".strip(),
        decision.evidence_refs,
        decision.confidence,
        action,
        amount if action in MONEY_ACTIONS else None,
        case["currency"],
        decision.rationale,
        {
            "missing_evidence": missing_evidence,
            "rejected_alternatives": rejected,
        },
    )
    max_rounds = max(1, int(getattr(get_settings(), "agent_max_negotiation_rounds", 2)))
    needs_counter = bool(data.get("needs_counter")) and int(state.get("rounds", 1)) < max_rounds
    return {
        "decision": decision.model_dump(mode="json"),
        "messages": [envelope],
        "needs_counter": needs_counter,
        "counter_context": (
            f"Resolution wants a counter to: {action} {amount}" if needs_counter else ""
        ),
        "rounds": int(state.get("rounds", 1)) + 1,
        "steps": [
            _step(
                "resolution",
                "resolution",
                "llm" if result.data else "fallback",
                f"Decision {action} {amount}" + ("" if result.data else " (deterministic fallback)"),
                {
                    "action": action,
                    "amount": str(amount),
                    "confidence": decision.confidence,
                    "reasoning": decision.reasoning,
                    "missing_evidence": missing_evidence,
                    "rejected_alternatives": rejected,
                    "policy_citations": policy_payload,
                    "needs_counter": needs_counter,
                    "policy_refs": policy_refs,
                },
                latency_ms=result.latency_ms,
                tokens=result.tokens_in + result.tokens_out,
                model=result.model,
                error=result.error,
            )
        ],
        "errors": [f"resolution llm: {result.error}"] if result.error else [],
    }


async def merchant_counter_node(state: AgentState) -> dict:
    """Bounded second round: the merchant must answer the resolution agent's question."""
    case = state["case"]
    envelope = _env(
        "merchant",
        "COUNTER",
        f"Merchant restates position after counter: {state.get('counter_context')}",
        case_evidence(case),
        0.7,
        "OFFER_PARTIAL",
        money(Decimal(str(case["amount"])) * Decimal("0.40")),
        case["currency"],
        "Second-round counter bounded by the partial band; no new evidence was introduced.",
    )
    return {
        "merchant": envelope,
        "messages": [envelope],
        "steps": [
            _step(
                "merchant_counter",
                "merchant",
                "counter",
                "Merchant counter-offer (round 2)",
                {"action": "OFFER_PARTIAL"},
            )
        ],
    }


def policy_gate_node(state: AgentState) -> dict:
    """Deterministic. Re-evaluates with the decision's real confidence and clamps everything."""
    case = state["case"]
    decision = dict(state["decision"])
    final = evaluate(
        PolicyInput(
            reason_code=case["reason_code"],
            amount=case["amount"],
            currency=case["currency"],
            merchant_currency=case.get("merchant_currency", "USD"),
            confidence=decision.get("confidence"),
            refundable_amount=(case.get("capture") or {}).get("refundable_amount"),
            seller_protection=(case.get("capture") or {}).get("seller_protection_status", "UNKNOWN"),
            tracking_status=(case.get("tracking") or {}).get("status", "UNKNOWN"),
            hours_to_deadline=case.get("hours_to_deadline"),
            dispute_status=case.get("paypal_status", "OPEN"),
        )
    )
    pre = state["policy"]
    action, amount = _clamp_decision(
        decision["action"], money(decision.get("amount")), decision.get("confidence", 0), pre
    )

    if final.decision == "deny":
        action, amount = "ESCALATE", Decimal("0.00")
        decision["requires_approval"] = True
        decision["policy_notes"] = [r.id for r in final.matched_rules]
    else:
        decision["requires_approval"] = final.requires_approval
        decision["policy_notes"] = [r.id for r in final.matched_rules]
        if action in MONEY_ACTIONS and amount > final.max_auto_amount:
            decision["requires_approval"] = True
        if action in MONEY_ACTIONS and amount > final.max_amount:
            action, amount = "ESCALATE", Decimal("0.00")

    decision.update({"action": action, "amount": str(amount), "currency": case["currency"]})
    return {
        "decision": decision,
        "policy": {
            **pre,
            "final": {
                "decision": final.decision,
                "requires_approval": decision["requires_approval"],
                "max_amount": str(final.max_amount),
                "max_auto_amount": str(final.max_auto_amount),
                "matched_rules": [
                    {"id": r.id, "outcome": r.outcome, "reason": r.reason}
                    for r in final.matched_rules
                ],
                "ruleset_version": final.ruleset_version,
            },
        },
        "steps": [
            _step(
                "policy_gate",
                "system",
                "policy",
                f"Policy: {final.decision}"
                + (" — approval required" if decision["requires_approval"] else ""),
                {
                    "decision": final.decision,
                    "rules": [r.id for r in final.matched_rules],
                    "max_auto_amount": str(final.max_auto_amount),
                },
            )
        ],
    }


def make_plan(case: dict, decision: dict, run_id: str) -> PaymentPlan | None:
    action = decision["action"]
    amount = money(decision.get("amount"))
    capture_id = (case.get("capture") or {}).get("paypal_capture_id")
    if action not in MONEY_ACTIONS or not capture_id or amount <= 0:
        return None
    key = sign_plan(
        {
            "dispute": case["paypal_dispute_id"],
            "action": action,
            "amount": str(amount),
            "capture": capture_id,
        }
    )[:32]
    plan = PaymentPlan(
        action=action,  # type: ignore[arg-type]
        amount=amount,
        currency=case["currency"],
        capture_id=capture_id,
        dispute_id=case["dispute_id"],
        run_id=run_id,
        idempotency_key=key,
        note=f"{action} for {case.get('case_number') or case.get('paypal_case_number')}",
    )
    plan.signature = sign_plan(plan.model_dump(mode="json", exclude={"signature"}))
    return plan


def payment_node(state: AgentState) -> dict:
    """Payment Agent: deterministic preflight, then emit (or refuse) a signed plan.

    This node has no PayPal client and no credentials. It can only describe an
    action inside the policy envelope; the signed-plan executor is the single
    component allowed to call the PayPal backend.
    """
    case = state["case"]
    decision = state["decision"]
    action = decision["action"]
    amount = money(decision.get("amount"))
    capture = case.get("capture") or {}
    capture_id = capture.get("paypal_capture_id")
    capture_status = str(capture.get("status") or "UNKNOWN")
    capture_currency = str(capture.get("currency") or case.get("currency") or "USD")
    refundable_before = money(
        capture.get("refundable_amount")
        if capture.get("refundable_amount") is not None
        else capture.get("amount")
    )
    requires_approval = bool(decision.get("requires_approval", True))

    checks = {
        "money_action": action in MONEY_ACTIONS,
        "capture_present": bool(capture_id),
        "capture_completed": capture_status == "COMPLETED",
        "positive_amount": amount > Decimal("0.00"),
        "currency_matches": capture_currency == str(case.get("currency") or "USD"),
        "within_refundable": amount <= refundable_before,
        "approval_decided": decision.get("requires_approval") is not None,
    }
    reasons = [name for name, passed in checks.items() if not passed]
    eligible = all(checks.values())
    execution_allowed = eligible and not requires_approval

    plan = make_plan(case, decision, state.get("run_id", "")) if eligible else None
    if plan is not None:
        expected = sign_plan(plan.model_dump(mode="json", exclude={"signature"}))
        if expected != plan.signature:
            reasons.append("plan_signature_invalid")
            eligible = False
            execution_allowed = False
            plan = None

    preflight = PaymentPreflight(
        eligible=eligible,
        execution_allowed=execution_allowed,
        requires_approval=requires_approval,
        checks=checks,
        reasons=reasons,
        refundable_before=refundable_before,
        refundable_after=max(Decimal("0.00"), refundable_before - amount) if eligible else refundable_before,
        currency=capture_currency,
    )
    if plan:
        summary = (
            "Payment preflight passed; signed plan awaits human approval"
            if requires_approval
            else "Payment preflight passed; signed plan ready for executor"
        )
    else:
        summary = f"No money movement for {action}: preflight refused"

    return {
        "payment_preflight": preflight.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json") if plan else None,
        "steps": [
            _step(
                "payment",
                "payment",
                "plan" if plan else "noop",
                summary,
                {
                    "action": action,
                    "amount": str(amount),
                    "capture": capture_id,
                    "preflight": preflight.model_dump(mode="json"),
                    "plan": plan.model_dump(mode="json") if plan else None,
                    "backend_call": "delegated_to_signed_plan_executor" if plan else None,
                },
            )
        ],
        "errors": [f"payment preflight: {', '.join(reasons)}"] if reasons else [],
    }


def route_after_resolution(state: AgentState) -> str:
    if state.get("needs_counter") and int(state.get("rounds", 1)) < 2:
        return "counter"
    return "gate"
