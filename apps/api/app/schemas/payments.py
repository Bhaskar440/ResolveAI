from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class CreateOrderRequest(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal(10000))
    currency: str = Field(default="USD", min_length=3, max_length=3)
    description: str = Field(min_length=1, max_length=127)
    invoice_id: str = Field(min_length=1, max_length=127)
    return_url: str | None = None
    cancel_url: str | None = None

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class PaymentCaptureOut(BaseModel):
    paypal_capture_id: str
    status: str
    amount: Decimal
    currency: str
    order_id: str | None = None
    seller_protection_status: str
    final_capture: bool
    simulated: bool = False


class PaymentOrderOut(BaseModel):
    paypal_order_id: str
    status: str
    amount: Decimal
    currency: str
    item_title: str | None = None
    invoice_id: str | None = None
    approval_url: str | None = None
    simulated: bool = False
    capture: PaymentCaptureOut | None = None
    persisted: bool = True


class RefundStatusOut(BaseModel):
    paypal_refund_id: str
    status: str
    amount: Decimal
    currency: str
    simulated: bool = False
