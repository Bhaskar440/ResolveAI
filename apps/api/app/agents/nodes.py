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
    PaymentPlan,
    RequestedAction,
)
from app.agents.llm import get_llm
from app.agents.policy.engine import PolicyInput, evaluate
from app.core.security import sign_plan

logger = logging.getLogger("resolveai.agents")
CENT = Decimal("0.01")


class AgentState(TypedDict, total=False):
    run_id: str
    case: dict[str, Any]
    policy: dict[str, Any]
    buyer: dict[str, Any]
    merchant: dict[str, Any]
    decision: dict[str, Any]
    plan: dict[str, Any] | None
    steps: Annotated[list[dict], operator.add]
    messages: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]
    rounds: int
    needs_counter: bool
    counter_context: str


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


BUYER_SYSTEM = """You are the BUYER agent in a PayPal dispute. Argue for the buyer's legitimate
remedy using ONLY the facts provided. Never invent tracking, messages or policy.
Return strict JSON: {"claim": str, "desired_action": "REFUND_FULL"|"REFUND_PARTIAL"|"ESCALATE",
"confidence": number 0..1, "rationale": str, "evidence_refs": [str]}."""

MERCHANT_SYSTEM = """You are the MERCHANT agent defending a seller in a PayPal dispute. Use ONLY the
facts provided. Minimise unjustified loss while keeping the customer. You may concede when the
evidence is against you. Return strict JSON: {"position": str,
"proposed_action": "REFUND_FULL"|"REFUND_PARTIAL"|"OFFER_PARTIAL"|"DEFEND"|"ESCALATE",
"amount": number, "confidence": number 0..1, "rationale": str, "evidence_refs": [str]}."""

RESOLUTION_SYSTEM = """You are the RESOLUTION agent: a neutral adjudicator. Pick exactly ONE action
from allowed_actions. Never exceed max_amount. Partial/offer amounts must sit inside
partial_band [low, high]. Confidence must reflect evidence quality, not optimism.
Return strict JSON: {"action": str, "amount": number, "confidence": number 0..1,
"rationale": str, "evidence_refs": [str], "needs_counter": boolean}."""


def _projection(case: dict, role: str) -> dict:
    base = {
        "reason_code": case.get("reason_code"),
        "reason_detail": case.get("reason_detail"),
        "amount": case.get("amount"),
        "currency": case.get("currency"),
        "order": case.get("order"),
        "messages": case.get("messages"),
    }
    if role == "buyer":
        base["tracking"] = case.get("tracking")
    elif role == "merchant":
        base["tracking"] = case.get("tracking")
        base["capture"] = case.get("capture")
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


async def buyer_node(state: AgentState) -> dict:
    case = state["case"]
    llm = get_llm()
    result = await llm.complete_json(
        BUYER_SYSTEM,
        json.dumps(_projection(case, "buyer"), default=str)[:6000],
        max_tokens=350,
    )
    data = result.data or {}
    action = data.get("desired_action")
    if action not in {"REFUND_FULL", "REFUND_PARTIAL", "ESCALATE"}:
        action = {
            "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "REFUND_FULL",
            "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "REFUND_FULL",
            "UNAUTHORISED": "ESCALATE",
        }.get(case["reason_code"], "REFUND_PARTIAL")
    confidence = data.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = {"REFUND_FULL": 0.86, "REFUND_PARTIAL": 0.7, "ESCALATE": 0.6}[action]
    claim = str(data.get("claim") or case.get("reason_detail") or "Buyer requests a remedy.")[:800]
    envelope = _env(
        "buyer",
        "PROPOSAL" if action != "ESCALATE" else "FINDING",
        claim,
        data.get("evidence_refs") or case_evidence(case),
        confidence,
        action,
        money(case["amount"]) if action == "REFUND_FULL" else None,
        case["currency"],
        str(data.get("rationale") or "Buyer statement and order facts."),
        {"max_amount": case["amount"]},
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
                {"action": action, "confidence": envelope["confidence"]},
                latency_ms=result.latency_ms,
                tokens=result.tokens_in + result.tokens_out,
                model=result.model,
                error=result.error,
            )
        ],
        "errors": [f"buyer llm: {result.error}"] if result.error else [],
    }


async def merchant_node(state: AgentState) -> dict:
    case = state["case"]
    llm = get_llm()
    result = await llm.complete_json(
        MERCHANT_SYSTEM,
        json.dumps(_projection(case, "merchant"), default=str)[:6000],
        max_tokens=350,
    )
    data = result.data or {}
    tracking = case.get("tracking") or {}
    fallback = {
        "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": "REFUND_FULL"
        if tracking.get("status") != "DELIVERED"
        else "DEFEND",
        "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": "OFFER_PARTIAL",
        "UNAUTHORISED": "DEFEND",
    }.get(case["reason_code"], "DEFEND")
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
    envelope = _env(
        "merchant",
        "PROPOSAL" if action != "ESCALATE" else "FINDING",
        str(data.get("position") or f"Merchant proposes {action}")[:800],
        data.get("evidence_refs") or case_evidence(case),
        confidence,
        action,
        amount,
        case["currency"],
        str(data.get("rationale") or "Merchant record and seller protection facts."),
        {"max_offer": case["amount"]},
    )
    summary = f"Merchant proposes {action}" + ("" if result.data else " (deterministic fallback)")
    return {
        "merchant": envelope,
        "messages": [envelope],
        "steps": [
            _step(
                "merchant",
                "merchant",
                "llm" if result.data else "fallback",
                summary,
                {"action": action, "amount": str(amount) if amount else None},
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
    context = {
        "case": _projection(case, "resolution"),
        "buyer": state.get("buyer"),
        "merchant": state.get("merchant"),
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
        json.dumps(context, default=str)[:8000],
        max_tokens=450,
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

    decision = AgentDecision(
        action=action,  # type: ignore[arg-type]
        amount=amount,
        currency=case["currency"],
        confidence=max(0.0, min(1.0, float(confidence))),
        rationale=str(data.get("rationale") or "Deterministic adjudication from policy + case facts.")[
            :2000
        ],
        evidence_refs=data.get("evidence_refs") or case_evidence(case),
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
    )
    needs_counter = bool(data.get("needs_counter")) and int(state.get("rounds", 1)) < 2
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
                    "needs_counter": needs_counter,
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
        note=f"{action} for {case.get('paypal_case_number')}",
    )
    plan.signature = sign_plan(plan.model_dump(mode="json", exclude={"signature"}))
    return plan


def payment_node(state: AgentState) -> dict:
    case = state["case"]
    decision = state["decision"]
    action = decision["action"]
    amount = money(decision["amount"])
    capture_id = (case.get("capture") or {}).get("paypal_capture_id")
    plan = make_plan(case, decision, state.get("run_id", ""))

    return {
        "plan": plan.model_dump(mode="json") if plan else None,
        "steps": [
            _step(
                "payment",
                "payment",
                "plan" if plan else "noop",
                "Payment plan signed" if plan else f"No money movement for {action}",
                {
                    "action": action,
                    "amount": str(amount),
                    "capture": capture_id,
                    "plan": plan.model_dump(mode="json") if plan else None,
                },
            )
        ],
    }


def route_after_resolution(state: AgentState) -> str:
    if state.get("needs_counter") and int(state.get("rounds", 1)) < 2:
        return "counter"
    return "gate"
