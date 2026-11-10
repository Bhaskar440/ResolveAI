"""PayPal adapter contract.

Two implementations, one interface:
  * replay  — reads fixtures/disputes/demo_scenarios.json (no network, default)
  * sandbox — real https://api-m.sandbox.paypal.com calls

The rest of the app never branches on mode; it just calls these methods and reads
`receipt.simulated` when it needs to label a result honestly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from pydantic import BaseModel, Field


class NormalizedOrder(BaseModel):
    paypal_order_id: str
    amount: Decimal
    currency: str = "USD"
    item_title: str | None = None
    created_at_paypal: datetime | None = None
    buyer_email: str | None = None


class NormalizedCapture(BaseModel):
    paypal_capture_id: str
    status: str = "COMPLETED"
    amount: Decimal
    currency: str = "USD"
    seller_protection_status: str = "UNKNOWN"
    refundable_amount: Decimal | None = None


class NormalizedMessage(BaseModel):
    direction: str = "inbound"
    author_type: str = "buyer"
    body: str
    sent_at: datetime | None = None
    paypal_message_id: str | None = None


class NormalizedDispute(BaseModel):
    paypal_dispute_id: str
    paypal_case_number: str | None = None
    reason_code: str
    reason_detail: str | None = None
    status: str = "OPEN"
    paypal_status: str = "OPEN"
    lifecycle_stage: str = "INQUIRY"
    amount: Decimal
    currency: str = "USD"
    response_due_by: datetime | None = None
    paypal_created_at: datetime | None = None
    buyer_label: str | None = None
    buyer_email_hash: str | None = None
    order: NormalizedOrder | None = None
    capture: NormalizedCapture | None = None
    tracking: dict[str, Any] | None = None
    risk_signals: list[str] = Field(default_factory=list)
    messages: list[NormalizedMessage] = Field(default_factory=list)
    scenario: str | None = None
    expected_outcome: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RefundReceipt(BaseModel):
    paypal_refund_id: str
    status: str
    amount: Decimal
    currency: str = "USD"
    simulated: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class PayPalError(RuntimeError):
    def __init__(self, status: int, code: str, message: str, debug_id: str | None = None):
        self.status = status
        self.code = code
        self.debug_id = debug_id
        super().__init__(f"{status} {code}: {message}")


class PayPalAdapter(Protocol):
    mode: str

    async def list_disputes(self) -> list[NormalizedDispute]: ...

    async def get_dispute(self, dispute_id: str) -> NormalizedDispute: ...

    async def refund(
        self,
        capture_id: str,
        amount: Decimal,
        currency: str,
        *,
        idempotency_key: str,
        note: str | None = None,
    ) -> RefundReceipt: ...

    async def verify_webhook(self, headers: dict[str, str], event: dict[str, Any]) -> bool: ...
