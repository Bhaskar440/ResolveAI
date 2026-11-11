"""Payment endpoints — real order -> approval -> capture -> PostgreSQL flow.

These routes exist so the payment lifecycle is testable without the demo scripts.
No agent can reach them; they are operator/API surface only. The capture route
asks PayPal for the order status first and refuses to capture an unapproved order.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import SessionDep, require_session
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.paypal.base import NormalizedCapture, NormalizedOrder, PayPalError
from app.schemas.payments import (
    CreateOrderRequest,
    PaymentCaptureOut,
    PaymentOrderOut,
    RefundStatusOut,
)
from app.services import payments

router = APIRouter(
    prefix="/payments", tags=["payments"], dependencies=[Depends(require_session)]
)
settings = get_settings()


def _paypal_error(exc: PayPalError) -> AppError:
    if exc.status == 404:
        return NotFoundError(
            "PayPal could not find that resource.",
            details={"paypal_code": exc.code, "debug_id": exc.debug_id},
        )
    return AppError(
        f"PayPal rejected the request ({exc.code}).",
        status_code=502,
        code="PAYPAL_ERROR",
        details={
            "paypal_status": exc.status,
            "paypal_code": exc.code,
            "debug_id": exc.debug_id,
        },
    )


def _capture_out(capture: NormalizedCapture | None) -> PaymentCaptureOut | None:
    if capture is None:
        return None
    return PaymentCaptureOut(
        paypal_capture_id=capture.paypal_capture_id,
        status=capture.status,
        amount=capture.amount,
        currency=capture.currency,
        order_id=capture.order_id,
        seller_protection_status=capture.seller_protection_status,
        final_capture=capture.final_capture,
        simulated=capture.simulated,
    )


def _order_out(order: NormalizedOrder) -> PaymentOrderOut:
    return PaymentOrderOut(
        paypal_order_id=order.paypal_order_id,
        status=order.status,
        amount=order.amount,
        currency=order.currency,
        item_title=order.item_title,
        invoice_id=order.invoice_id,
        approval_url=order.approval_url,
        simulated=order.simulated,
        capture=_capture_out(order.capture),
    )


@router.post("/orders", response_model=PaymentOrderOut, status_code=201)
async def create_order(body: CreateOrderRequest, session: SessionDep) -> PaymentOrderOut:
    try:
        _, order = await payments.create_checkout_order(
            session,
            amount=body.amount,
            currency=body.currency,
            description=body.description,
            invoice_id=body.invoice_id,
            return_url=body.return_url or f"{settings.web_base_url}/",
            cancel_url=body.cancel_url or f"{settings.web_base_url}/",
        )
    except PayPalError as exc:
        raise _paypal_error(exc) from exc
    return _order_out(order)


@router.get("/orders/{paypal_order_id}", response_model=PaymentOrderOut)
async def get_order(paypal_order_id: str, session: SessionDep) -> PaymentOrderOut:
    try:
        _, order = await payments.refresh_order(session, paypal_order_id)
    except KeyError as exc:
        raise NotFoundError("Order not found in replay mode.") from exc
    except PayPalError as exc:
        raise _paypal_error(exc) from exc
    return _order_out(order)


@router.post("/orders/{paypal_order_id}/capture", response_model=PaymentOrderOut)
async def capture_order(
    paypal_order_id: str,
    session: SessionDep,
    idempotency_key: str | None = Query(default=None, max_length=108),
) -> PaymentOrderOut:
    try:
        _, order = await payments.capture_approved_order(
            session, paypal_order_id=paypal_order_id, idempotency_key=idempotency_key
        )
    except payments.OrderNotApprovedError as exc:
        raise AppError(
            "PayPal has not received the buyer's approval yet.",
            status_code=409,
            code="ORDER_NOT_APPROVED",
            details={"order_id": exc.order_id, "paypal_status": exc.status},
        ) from exc
    except payments.PaymentStateError as exc:
        raise AppError(
            str(exc),
            status_code=409,
            code="PAYMENT_STATE_INVALID",
        ) from exc
    except KeyError as exc:
        raise NotFoundError("Order not found in replay mode.") from exc
    except PayPalError as exc:
        raise _paypal_error(exc) from exc
    return _order_out(order)


@router.get("/captures/{capture_id}", response_model=PaymentCaptureOut)
async def get_capture(capture_id: str) -> PaymentCaptureOut:
    try:
        capture = await payments.get_capture_details(capture_id)
    except KeyError as exc:
        raise NotFoundError("Capture not found in replay mode.") from exc
    except PayPalError as exc:
        raise _paypal_error(exc) from exc
    out = _capture_out(capture)
    assert out is not None
    return out


@router.get("/refunds/{refund_id}", response_model=RefundStatusOut)
async def get_refund(refund_id: str) -> RefundStatusOut:
    try:
        receipt = await payments.get_refund_details(refund_id)
    except KeyError as exc:
        raise NotFoundError("Refund not found in replay mode.") from exc
    except PayPalError as exc:
        raise _paypal_error(exc) from exc
    return RefundStatusOut(
        paypal_refund_id=receipt.paypal_refund_id,
        status=receipt.status,
        amount=receipt.amount,
        currency=receipt.currency,
        simulated=receipt.simulated,
    )
