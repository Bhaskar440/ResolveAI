"""Typed contracts shared by agents, gate and executor.

Free text is confined to `rationale`/`summary`. Everything that can move money is a
number in a validated model, so the gate can check it without parsing prose.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

ActionType = Literal[
    "REFUND_FULL",
    "REFUND_PARTIAL",
    "OFFER_PARTIAL",
    "ACCEPT_CLAIM",
    "DEFEND",
    "ESCALATE",
]

BuyerRequest = Literal[
    "REFUND_FULL",
    "REFUND_PARTIAL",
    "REPLACEMENT",
    "ESCALATE",
    "UNKNOWN",
]

MONEY_ACTIONS = {"REFUND_FULL", "REFUND_PARTIAL", "OFFER_PARTIAL", "ACCEPT_CLAIM"}


class RequestedAction(BaseModel):
    action: ActionType
    amount: Decimal | None = None
    currency: str = "USD"


class AgentEnvelope(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    sender: Literal["buyer", "merchant", "resolution", "payment"]
    to: Literal["buyer", "merchant", "resolution", "payment", "system"] = "resolution"
    type: Literal[
        "FINDING", "QUESTION", "PROPOSAL", "COUNTER", "ACCEPT", "REJECT", "DECISION"
    ]
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)
    constraints: dict = Field(default_factory=dict)
    requested_action: RequestedAction | None = None
    rationale: str = ""


class BuyerIntake(BaseModel):
    """What the Buyer Agent extracted before anyone argues about money."""

    summary: str
    transaction_id: str | None = None
    reason_code: str
    requested_resolution: BuyerRequest = "UNKNOWN"
    requested_amount: Decimal | None = None
    missing_information: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    source: str = "deterministic"


class PolicyCitation(BaseModel):
    chunk_id: str
    title: str
    text: str
    score: float
    source: str
    document: str = ""
    section: str = ""
    category: str = ""
    retrieval_mode: str = "vector"
    embedding_model: str = ""


class MerchantEvidence(BaseModel):
    """Structured evidence returned by the Merchant Agent."""

    order: dict = Field(default_factory=dict)
    shipping: dict = Field(default_factory=dict)
    capture: dict = Field(default_factory=dict)
    seller_protection: str = "UNKNOWN"
    policies: list[PolicyCitation] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    source: str = "deterministic"


class AgentDecision(BaseModel):
    action: ActionType
    amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    confidence: float = Field(ge=0, le=1)
    rationale: str
    reasoning: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    rejected_alternatives: list[dict] = Field(default_factory=list)
    policy_citations: list[PolicyCitation] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)
    requires_approval: bool = False


class PaymentPreflight(BaseModel):
    """The Payment Agent's deterministic gate before a signed plan exists."""

    eligible: bool = False
    execution_allowed: bool = False
    requires_approval: bool = True
    checks: dict[str, bool] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    refundable_before: Decimal = Decimal("0.00")
    refundable_after: Decimal = Decimal("0.00")
    currency: str = "USD"


class PaymentPlan(BaseModel):
    action: ActionType
    amount: Decimal
    currency: str
    capture_id: str | None
    dispute_id: str
    run_id: str
    idempotency_key: str
    note: str | None = None
    signature: str = ""
    simulated: bool = True
