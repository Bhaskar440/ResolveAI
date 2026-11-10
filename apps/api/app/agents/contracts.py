"""Typed contracts shared by agents, gate and executor.

Free text is confined to `rationale`. Everything that can move money is a number
in a validated model, so the gate can check it without parsing prose.
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

MONEY_ACTIONS = {"REFUND_FULL", "REFUND_PARTIAL", "OFFER_PARTIAL", "ACCEPT_CLAIM"}


class RequestedAction(BaseModel):
    action: ActionType
    amount: Decimal | None = None
    currency: str = "USD"


class AgentEnvelope(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid4().hex[:12]}")
    sender: Literal["buyer", "merchant", "resolution", "payment"]
    to: Literal["buyer", "merchant", "resolution", "payment", "system"] = "resolution"
    type: Literal["FINDING", "PROPOSAL", "COUNTER", "ACCEPT", "REJECT", "DECISION"]
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1, default=0.5)
    constraints: dict = Field(default_factory=dict)
    requested_action: RequestedAction | None = None
    rationale: str = ""


class AgentDecision(BaseModel):
    action: ActionType
    amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    policy_notes: list[str] = Field(default_factory=list)
    requires_approval: bool = False


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
