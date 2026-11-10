"""Payment lifecycle — orders, captures, and reconciliation.

This is the app-level path for Phase 2 (order -> buyer approval -> capture ->
PostgreSQL). It is deliberately separate from the agent path: agents never call
these methods, and only the executor can refund.

Every write is idempotent on PayPal ids: orders on `paypal_order_id`, captures on
`paypal_capture_id`. Re-running a capture after PayPal already captured the order
returns the stored row instead of charging twice.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import pii_hash
from app.db.models import Capture, Merchant, Order
from app.paypal.base import NormalizedCapture, NormalizedOrder
from app.paypal.factory import get_adapter
from app.services.ingestion import get_or_create_merchant

logger = logging.getLogger("resolveai.payments")


class OrderNotApprovedError(RuntimeError):
    """PayPal has not received the buyer's approval yet — capture would be premature."""

    def __init__(self, order_id: str, status: str) -> None:
        self.order_id = order_id
        self.status = status
        super().__init__(f"order {order_id} is {status}, not APPROVED")


class PaymentStateError(RuntimeError):
    """PayPal returned a state this workflow cannot advance from."""


def _buyer_label(email: str | None) -> str | None:
    return email.split("@")[0][:24] if email else None


async def persist_capture(
    session: AsyncSession,
    merchant: Merchant,
    order_row: Order,
    capture: NormalizedCapture,
    *,
    commit: bool = False,
) -> Capture:
    row = (
        await session.execute(
            select(Capture).where(Capture.paypal_capture_id == capture.paypal_capture_id)
        )
    ).scalar_one_or_none()
    raw = {
        **capture.raw,
        "mode": "replay" if capture.simulated else "sandbox",
        "simulated": capture.simulated,
    }
    if row is None:
        row = Capture(
            merchant_id=merchant.id,
            order_id=order_row.id,
            paypal_capture_id=capture.paypal_capture_id,
            status=capture.status,
            amount=capture.amount,
            currency=capture.currency,
            seller_protection_status=capture.seller_protection_status,
            final_capture=capture.final_capture,
            raw=raw,
        )
        session.add(row)
        await session.flush()
        logger.info("stored capture %s (%s)", capture.paypal_capture_id, capture.status)
    else:
        row.status = capture.status
        row.amount = capture.amount
        row.currency = capture.currency
        row.seller_protection_status = capture.seller_protection_status
        row.final_capture = capture.final_capture
        row.raw = raw
    if commit:
        await session.commit()
    return row


async def persist_order(
    session: AsyncSession,
    merchant: Merchant,
    order: NormalizedOrder,
    *,
    commit: bool = False,
) -> Order:
    if not order.paypal_order_id:
        raise PaymentStateError("PayPal returned an order without an id")

    row = (
        await session.execute(
            select(Order).where(Order.paypal_order_id == order.paypal_order_id)
        )
    ).scalar_one_or_none()
    raw = {
        **order.raw,
        "mode": "replay" if order.simulated else "sandbox",
        "simulated": order.simulated,
        "invoice_id": order.invoice_id,
        "approval_url": order.approval_url,
    }
    buyer_hash = pii_hash(order.buyer_email) if order.buyer_email else None
    if row is None:
        row = Order(
            merchant_id=merchant.id,
            paypal_order_id=order.paypal_order_id,
            status=order.status,
            amount=order.amount,
            currency=order.currency,
            buyer_email_hash=buyer_hash,
            buyer_label=_buyer_label(order.buyer_email),
            item_title=order.item_title,
            raw=raw,
        )
        session.add(row)
        await session.flush()
        logger.info("stored order %s (%s)", order.paypal_order_id, order.status)
    else:
        row.status = order.status
        row.amount = order.amount
        row.currency = order.currency
        row.item_title = order.item_title or row.item_title
        row.buyer_email_hash = buyer_hash or row.buyer_email_hash
        row.buyer_label = _buyer_label(order.buyer_email) or row.buyer_label
        row.raw = raw

    if order.capture is not None:
        await persist_capture(session, merchant, row, order.capture)

    if commit:
        await session.commit()
    return row


async def create_checkout_order(
    session: AsyncSession,
    *,
    amount: Decimal,
    currency: str,
    description: str,
    invoice_id: str,
    return_url: str | None = None,
    cancel_url: str | None = None,
) -> tuple[Order, NormalizedOrder]:
    merchant = await get_or_create_merchant(session)
    adapter = get_adapter()
    order = await adapter.create_order(
        amount=amount,
        currency=currency,
        description=description,
        invoice_id=invoice_id,
        return_url=return_url,
        cancel_url=cancel_url,
        idempotency_key=f"resolveai-order-{invoice_id}",
    )
    row = await persist_order(session, merchant, order)
    await session.commit()
    return row, order


async def refresh_order(session: AsyncSession, paypal_order_id: str) -> tuple[Order, NormalizedOrder]:
    merchant = await get_or_create_merchant(session)
    adapter = get_adapter()
    order = await adapter.get_order(paypal_order_id)
    row = await persist_order(session, merchant, order)
    await session.commit()
    return row, order


async def capture_approved_order(
    session: AsyncSession,
    *,
    paypal_order_id: str,
    idempotency_key: str | None = None,
) -> tuple[Order, NormalizedOrder]:
    """Capture only after PayPal itself reports the order as APPROVED.

    Re-running this after a successful capture is safe: PayPal reports COMPLETED
    and the existing capture is returned from the database.
    """
    merchant = await get_or_create_merchant(session)
    adapter = get_adapter()
    remote = await adapter.get_order(paypal_order_id)

    if remote.status == "COMPLETED":
        if remote.capture is None:
            raise PaymentStateError(
                f"PayPal reports order {paypal_order_id} COMPLETED but returned no capture"
            )
        row = await persist_order(session, merchant, remote)
        await session.commit()
        logger.info("order %s was already captured", paypal_order_id)
        return row, remote

    if remote.status != "APPROVED":
        raise OrderNotApprovedError(paypal_order_id, remote.status)

    key = idempotency_key or f"resolveai-capture-{paypal_order_id}"
    captured = await adapter.capture_order(paypal_order_id, idempotency_key=key)
    if captured.capture is None:
        raise PaymentStateError(
            f"capture for order {paypal_order_id} returned status {captured.status} "
            "without a capture id"
        )
    row = await persist_order(session, merchant, captured)
    await session.commit()
    return row, captured


async def get_capture_details(capture_id: str) -> NormalizedCapture:
    return await get_adapter().get_capture(capture_id)


async def get_refund_details(refund_id: str):
    return await get_adapter().get_refund(refund_id)
