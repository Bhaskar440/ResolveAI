"""Deterministic policy engine.

This module is the reason an LLM can never move money on its own:
`evaluate()` produces an *envelope* (allowed actions, ceiling, approval requirement)
that the gate and the executor both enforce, independently of anything a model says.

Pure functions, no I/O beyond loading rules.yaml once, no network, no DB.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).with_name("rules.yaml")
CENT = Decimal("0.01")


@dataclass(frozen=True)
class PolicyInput:
    reason_code: str
    amount: Decimal | float | int
    currency: str = "USD"
    merchant_currency: str = "USD"
    confidence: float | None = None
    refundable_amount: Decimal | float | None = None
    seller_protection: str = "UNKNOWN"  # ELIGIBLE | NOT_ELIGIBLE | UNKNOWN
    tracking_status: str = "UNKNOWN"  # DELIVERED | IN_TRANSIT | NO_TRACKING | UNKNOWN
    hours_to_deadline: float | None = None
    dispute_status: str = "OPEN"


@dataclass(frozen=True)
class MatchedRule:
    id: str
    outcome: str  # deny | require_approval | note
    reason: str


@dataclass(frozen=True)
class PolicyResult:
    decision: str  # allow | require_approval | deny
    allowed_actions: list[str]
    requires_approval: bool
    max_amount: Decimal  # absolute ceiling the gate will ever accept
    max_auto_amount: Decimal  # what may execute with no human
    partial_band: tuple[Decimal, Decimal] | None
    confidence_band: str  # high | medium | low | none
    matched_rules: list[MatchedRule] = field(default_factory=list)
    ruleset_version: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["max_amount"] = str(self.max_amount)
        data["max_auto_amount"] = str(self.max_auto_amount)
        data["partial_band"] = [str(x) for x in self.partial_band] if self.partial_band else None
        return data


@lru_cache(maxsize=4)
def load_rules(path: str | None = None) -> dict[str, Any]:
    with open(path or RULES_PATH, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _money(value: Decimal | float | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(CENT)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _band(confidence: float | None, rules: dict[str, Any]) -> str:
    if confidence is None:
        return "none"
    th = rules["thresholds"]
    if confidence >= th["auto_approve_confidence"]:
        return "high"
    if confidence >= th["escalate_confidence"]:
        return "medium"
    return "low"


def inputs_digest(inp: PolicyInput) -> str:
    payload = {
        "reason_code": inp.reason_code,
        "amount": str(_money(inp.amount)),
        "currency": inp.currency,
        "merchant_currency": inp.merchant_currency,
        "confidence": inp.confidence,
        "refundable_amount": None
        if inp.refundable_amount is None
        else str(_money(inp.refundable_amount)),
        "seller_protection": inp.seller_protection,
        "tracking_status": inp.tracking_status,
        "hours_to_deadline": inp.hours_to_deadline,
        "dispute_status": inp.dispute_status,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def evaluate(inp: PolicyInput, rules: dict[str, Any] | None = None) -> PolicyResult:
    rules = rules or load_rules()
    th = rules["thresholds"]
    version = str(rules["version"])
    matched: list[MatchedRule] = []

    amount = _money(inp.amount)
    refundable = None if inp.refundable_amount is None else _money(inp.refundable_amount)
    band = _band(inp.confidence, rules)

    actions = list(
        rules["actions_by_reason"].get(
            inp.reason_code, rules["actions_by_reason"]["default"]
        )
    )
    money_actions = set(rules["money_actions"])

    def result(
        decision: str,
        *,
        actions_out: list[str],
        requires_approval: bool,
        max_amount: Decimal,
        max_auto: Decimal,
        band_out: str = band,
    ) -> PolicyResult:
        raw_band = rules["partial_bands"].get(
            inp.reason_code, rules["partial_bands"]["default"]
        )
        lo, hi = Decimal(str(raw_band[0])), Decimal(str(raw_band[1]))
        ceiling = max_amount
        return PolicyResult(
            decision=decision,
            allowed_actions=actions_out,
            requires_approval=requires_approval,
            max_amount=ceiling,
            max_auto_amount=max_auto,
            partial_band=(amount * lo, amount * hi),
            confidence_band=band_out,
            matched_rules=list(matched),
            ruleset_version=version,
        )

    # --- hard denials -------------------------------------------------------
    if inp.dispute_status.upper() in {"RESOLVED", "CLOSED", "OTHER"}:
        matched.append(MatchedRule("DENY_DISPUTE_CLOSED", "deny", "Dispute is already closed."))
        return result("deny", actions_out=[], requires_approval=False, max_amount=Decimal("0.00"), max_auto=Decimal("0.00"))

    if inp.currency.upper() != inp.merchant_currency.upper():
        matched.append(
            MatchedRule(
                "DENY_CURRENCY_MISMATCH",
                "deny",
                f"Dispute is {inp.currency} but merchant settles in {inp.merchant_currency}.",
            )
        )
        return result("deny", actions_out=[], requires_approval=False, max_amount=Decimal("0.00"), max_auto=Decimal("0.00"))

    # --- envelope ceiling ---------------------------------------------------
    ceiling = amount
    if refundable is not None and refundable < ceiling:
        ceiling = refundable
        matched.append(
            MatchedRule(
                "CLAMP_REFUNDABLE_BALANCE",
                "note",
                f"Refundable balance is {refundable} — ceiling lowered accordingly.",
            )
        )
    if ceiling > _money(th["hard_cap"]):
        ceiling = _money(th["hard_cap"])
        matched.append(
            MatchedRule(
                "CLAMP_HARD_CAP",
                "note",
                f"Merchant hard cap is {th['hard_cap']}.",
            )
        )

    # --- no money left to move ---------------------------------------------
    if refundable is not None and refundable <= Decimal("0.00"):
        actions = [a for a in actions if a not in money_actions]
        matched.append(
            MatchedRule("NO_REFUNDABLE_BALANCE", "note", "Nothing left to refund on this capture.")
        )

    # --- money actions only when something is refundable --------------------
    if refundable is None:
        actions = [a for a in actions if a not in money_actions]
        matched.append(
            MatchedRule("NO_CAPTURE_FACTS", "note", "Refundable amount unknown — money actions withheld.")
        )

    # --- low confidence: no automatic money, human decides -------------------
    if band in {"low", "none"}:
        matched.append(
            MatchedRule(
                "LOW_CONFIDENCE_NO_AUTO",
                "require_approval",
                f"Confidence {inp.confidence} is below the escalation threshold {th['escalate_confidence']}.",
            )
        )
        safe = [a for a in actions if a not in money_actions]
        return result(
            "require_approval",
            actions_out=safe,
            requires_approval=True,
            max_amount=ceiling,
            max_auto=Decimal("0.00"),
            band_out=band,
        )

    # --- deadline pressure: drop slow-moving offer paths --------------------
    if inp.hours_to_deadline is not None and inp.hours_to_deadline < float(
        th["deadline_pressure_hours"]
    ):
        if "OFFER_PARTIAL" in actions:
            actions.remove("OFFER_PARTIAL")
        matched.append(
            MatchedRule(
                "DEADLINE_PRESSURE",
                "note",
                f"{inp.hours_to_deadline:.1f}h to respond — offer flows excluded, decide now.",
            )
        )

    # --- approval triggers --------------------------------------------------
    requires_approval = False

    if inp.reason_code in set(rules["fraud_reasons"]):
        requires_approval = True
        matched.append(
            MatchedRule(
                "FRAUD_REASON_ALWAYS_HUMAN",
                "require_approval",
                f"Reason {inp.reason_code} is never auto-adjudicated.",
            )
        )

    if amount > _money(th["hard_cap"]):
        requires_approval = True
        matched.append(
            MatchedRule(
                "AMOUNT_ABOVE_HARD_CAP",
                "require_approval",
                f"{amount} exceeds the hard cap {th['hard_cap']}.",
            )
        )
    elif amount > _money(th["auto_resolve_cap"]):
        requires_approval = True
        matched.append(
            MatchedRule(
                "AMOUNT_ABOVE_AUTO_CAP",
                "require_approval",
                f"{amount} exceeds the autonomous cap {th['auto_resolve_cap']}.",
            )
        )

    if band == "medium":
        requires_approval = True
        matched.append(
            MatchedRule(
                "CONFIDENCE_REQUIRES_HUMAN",
                "require_approval",
                f"Confidence {inp.confidence} is below {th['auto_approve_confidence']}.",
            )
        )

    max_auto = Decimal("0.00") if requires_approval else min(ceiling, _money(th["auto_resolve_cap"]))

    return result(
        "require_approval" if requires_approval else "allow",
        actions_out=actions,
        requires_approval=requires_approval,
        max_amount=ceiling,
        max_auto=max_auto,
    )
