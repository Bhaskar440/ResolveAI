from __future__ import annotations

from decimal import Decimal

import pytest

from app.agents.policy.engine import PolicyInput, evaluate, inputs_digest, load_rules


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def test_inr_within_cap_low_confidence_needs_approval(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal("80.00"),
            confidence=0.62,
            refundable_amount=Decimal("80.00"),
            tracking_status="DELIVERED",
        ),
        rules,
    )
    assert r.decision == "require_approval"
    assert r.requires_approval is True
    assert "REFUND_FULL" in r.allowed_actions
    assert r.max_auto_amount == Decimal("0.00")
    assert {m.id for m in r.matched_rules} >= {"AMOUNT_ABOVE_AUTO_CAP", "CONFIDENCE_REQUIRES_HUMAN"}


def test_small_confident_refund_is_autonomous(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal("40.00"),
            confidence=0.93,
            refundable_amount=Decimal("40.00"),
        ),
        rules,
    )
    assert r.decision == "allow"
    assert r.requires_approval is False
    assert r.max_auto_amount == Decimal("40.00")


def test_unauthorised_never_auto_even_when_tiny(rules):
    r = evaluate(
        PolicyInput(
            reason_code="UNAUTHORISED",
            amount=Decimal("5.00"),
            confidence=0.99,
            refundable_amount=Decimal("5.00"),
        ),
        rules,
    )
    assert r.requires_approval is True
    assert "REFUND_FULL" not in r.allowed_actions
    assert any(m.id == "FRAUD_REASON_ALWAYS_HUMAN" for m in r.matched_rules)


def test_closed_dispute_denied(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal(10),
            confidence=0.9,
            refundable_amount=Decimal(10),
            dispute_status="RESOLVED",
        ),
        rules,
    )
    assert r.decision == "deny"
    assert r.allowed_actions == []


def test_currency_mismatch_denied(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal(10),
            currency="EUR",
            merchant_currency="USD",
            confidence=0.9,
        ),
        rules,
    )
    assert r.decision == "deny"


def test_no_refundable_balance_withholds_money_actions(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
            amount=Decimal(60),
            confidence=0.9,
            refundable_amount=Decimal("0.00"),
        ),
        rules,
    )
    assert "REFUND_FULL" not in r.allowed_actions
    assert "REFUND_PARTIAL" not in r.allowed_actions
    assert "DEFEND" in r.allowed_actions


def test_unknown_confidence_is_not_autonomous(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal(10),
            confidence=None,
            refundable_amount=Decimal(10),
        ),
        rules,
    )
    assert r.requires_approval is True
    assert r.confidence_band == "none"


def test_hard_cap_clamps_envelope(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
            amount=Decimal("500.00"),
            confidence=0.95,
            refundable_amount=Decimal("500.00"),
        ),
        rules,
    )
    assert r.max_amount == Decimal("250.00")
    assert r.requires_approval is True


def test_deadline_pressure_removes_offers(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
            amount=Decimal(40),
            confidence=0.9,
            refundable_amount=Decimal(40),
            hours_to_deadline=2.0,
        ),
        rules,
    )
    assert "OFFER_PARTIAL" not in r.allowed_actions


def test_partial_band_for_snad(rules):
    r = evaluate(
        PolicyInput(
            reason_code="MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
            amount=Decimal(100),
            confidence=0.9,
            refundable_amount=Decimal(100),
        ),
        rules,
    )
    assert r.partial_band == (Decimal("25.00"), Decimal("60.00"))


def test_digest_is_stable_and_sensitive():
    a = PolicyInput(reason_code="X", amount=Decimal("10.00"), confidence=0.5)
    b = PolicyInput(reason_code="X", amount=Decimal("10.0"), confidence=0.5)
    c = PolicyInput(reason_code="X", amount=Decimal("11.00"), confidence=0.5)
    assert inputs_digest(a) == inputs_digest(b)
    assert inputs_digest(a) != inputs_digest(c)
