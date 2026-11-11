from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DBStatus(BaseModel):
    connected: bool
    latency_ms: float
    server_version: str | None = None
    error: str | None = None


class Counts(BaseModel):
    disputes: int = 0
    runs: int = 0
    refunds: int = 0


class SystemStatus(BaseModel):
    status: str = Field(description="ok | degraded")
    app: str
    env: str
    mode: str
    checked_at: datetime
    db: DBStatus
    counts: Counts
    schema_tables: int
    capabilities: dict[str, bool]
    request_id: str


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paypal_dispute_id: str
    paypal_case_number: str | None = None
    buyer_label: str | None = None
    reason_code: str
    reason_detail: str | None = None
    status: str
    paypal_status: str
    lifecycle_stage: str
    amount: Decimal
    currency: str
    confidence: Decimal | None = None
    decision_code: str | None = None
    requires_approval: bool
    agent_summary: str | None = None
    response_due_by: datetime | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    recovered_amount: Decimal | None = None
    is_demo: bool


class DisputeList(BaseModel):
    items: list[DisputeOut]
    total: int
    limit: int
    offset: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paypal_order_id: str
    item_title: str | None = None
    amount: Decimal
    currency: str
    status: str


class CaptureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    paypal_capture_id: str
    status: str
    amount: Decimal
    currency: str
    seller_protection_status: str


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: str
    channel: str = "paypal"
    author_type: str
    body: str
    sent_at: datetime | None = None
    created_at: datetime | None = None


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ComplaintOut(BaseModel):
    dispute_id: UUID
    paypal_case_number: str | None = None
    paypal_dispute_id: str
    buyer_label: str | None = None
    reason_code: str
    reason_detail: str | None = None
    status: str
    amount: Decimal
    currency: str
    response_due_by: datetime | None = None
    created_at: datetime
    message_count: int = 0
    last_message: str | None = None
    last_message_at: datetime | None = None
    last_message_direction: str | None = None


class ComplaintList(BaseModel):
    items: list[ComplaintOut]
    total: int
    limit: int
    offset: int


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispute_id: UUID
    status: str
    trigger: str
    iterations: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    model_primary: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime


class StepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    node: str
    agent: str
    step_type: str
    summary: str | None = None
    payload: dict = Field(default_factory=dict)
    latency_ms: int | None = None
    tokens: int | None = None
    created_at: datetime


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    from_agent: str
    to_agent: str
    msg_type: str
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: Decimal | None = None
    constraints: dict = Field(default_factory=dict)
    rationale: str | None = None


class RunDetail(BaseModel):
    run: RunOut
    steps: list[StepOut]
    messages: list[AgentMessageOut]


class DecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    decision_code: str
    amount: Decimal
    currency: str
    confidence: Decimal | None = None
    rationale: str | None = None
    reasoning: str | None = None
    missing_evidence: list[str] = Field(default_factory=list)
    policy_citations: list[dict[str, Any]] = Field(default_factory=list)
    cited_evidence: list[str] = Field(default_factory=list)
    requires_approval: bool
    status: str
    decided_by: str
    created_at: datetime


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dispute_id: UUID
    decision_id: UUID
    status: str
    requested_at: datetime
    expires_at: datetime | None = None
    resolved_at: datetime | None = None
    note: str | None = None
    decision_code: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None
    case_number: str | None = None
    reason_code: str | None = None


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paypal_refund_id: str | None = None
    amount: Decimal
    currency: str
    status: str
    reason: str | None = None
    initiated_by: str
    simulated: bool = False
    created_at: datetime


class PolicyEvalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ruleset_version: str
    result: str
    matched_rules: list[dict] = Field(default_factory=list)
    envelope: dict = Field(default_factory=dict)
    created_at: datetime


class DisputeDetail(BaseModel):
    dispute: DisputeOut
    order: OrderOut | None = None
    capture: CaptureOut | None = None
    messages: list[MessageOut] = Field(default_factory=list)
    latest_run: RunOut | None = None
    decision: DecisionOut | None = None
    policy: PolicyEvalOut | None = None
    approvals: list[ApprovalOut] = Field(default_factory=list)
    refunds: list[RefundOut] = Field(default_factory=list)


class Metrics(BaseModel):
    open_disputes: int
    awaiting_approval: int
    resolved: int
    escalated: int
    pending_approvals: int
    total_at_risk: Decimal
    recovered: Decimal
    auto_executed: int
    human_executed: int
    median_run_seconds: float | None = None
    by_reason: dict[str, int]


class SeedResult(BaseModel):
    merchant: str
    disputes: int
    mode: str
    created: bool
    knowledge: dict[str, Any] | None = None


class ApprovalDecision(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)
    edited_amount: Decimal | None = Field(default=None, ge=0)


class StatusCount(BaseModel):
    status: str
    count: int


class ReasonBreakdown(BaseModel):
    reason_code: str
    count: int
    at_risk: Decimal
    resolved: int
    refunded: Decimal


class RefundSummary(BaseModel):
    count: int
    completed: int
    pending: int
    failed: int
    simulated: int
    live: int
    amount_total: Decimal
    amount_completed: Decimal
    amount_simulated: Decimal


class TrendPoint(BaseModel):
    date: str
    created: int
    resolved: int


class Analytics(BaseModel):
    total_disputes: int
    resolved_cases: int
    pending_cases: int
    escalated_cases: int
    awaiting_approval: int
    resolution_rate: float
    total_at_risk: Decimal
    refunded_total: Decimal
    by_status: list[StatusCount]
    by_reason: list[ReasonBreakdown]
    refunds: RefundSummary
    trend: list[TrendPoint]
    median_run_seconds: float | None = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class SessionUser(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: str
    merchant_id: UUID
    merchant_name: str
    merchant_slug: str


class SessionOut(BaseModel):
    user: SessionUser
    expires_at: datetime
    mode: str
