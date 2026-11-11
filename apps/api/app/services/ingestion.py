"""Dispute ingestion — the only place PayPal payloads become database rows.

Idempotent by construction: disputes are unique on (merchant, paypal_dispute_id),
orders on paypal_order_id, captures on paypal_capture_id, messages on
(dispute, dedupe key). Re-running a sync never duplicates anything.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import pii_hash
from app.db.models import (
    Capture,
    Dispute,
    DisputeMessage,
    DisputeStatusHistory,
    Merchant,
    Order,
)
from app.paypal.base import NormalizedDispute

logger = logging.getLogger("resolveai.ingestion")


async def get_or_create_merchant(session: AsyncSession) -> Merchant:
    from app.core.config import get_settings

    settings = get_settings()
    merchant = (
        await session.execute(
            select(Merchant).where(Merchant.slug == settings.demo_merchant_slug)
        )
    ).scalar_one_or_none()
    if merchant is None:
        merchant = Merchant(
            name=settings.demo_merchant_name,
            slug=settings.demo_merchant_slug,
            currency="USD",
            autonomy_enabled=True,
            auto_resolve_cap=Decimal("50.00"),
            auto_offer_cap=Decimal("100.00"),
            approval_required_above=Decimal("50.00"),
            risk_appetite="balanced",
        )
        session.add(merchant)
        await session.flush()
        logger.info("created merchant %s", merchant.slug)
    return merchant


def _dedupe_key(external_id: str | None, body: str, sent_at) -> str:
    raw = external_id or f"{body}:{sent_at}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


async def ingest_dispute(
    session: AsyncSession, merchant: Merchant, payload: NormalizedDispute
) -> Dispute:
    order_row: Order | None = None
    if payload.order:
        order_row = (
            await session.execute(
                select(Order).where(Order.paypal_order_id == payload.order.paypal_order_id)
            )
        ).scalar_one_or_none()
        if order_row is None:
            order_row = Order(
                merchant_id=merchant.id,
                paypal_order_id=payload.order.paypal_order_id,
                status="COMPLETED",
                amount=payload.order.amount,
                currency=payload.order.currency,
                buyer_email_hash=pii_hash(payload.order.buyer_email)
                if payload.order.buyer_email
                else payload.buyer_email_hash,
                buyer_label=payload.buyer_label,
                item_title=payload.order.item_title,
                raw={
                    "tracking": payload.tracking,
                    "shipping": (payload.raw or {}).get("shipping"),
                },
            )
            session.add(order_row)
            await session.flush()

    capture_row: Capture | None = None
    if payload.capture:
        capture_row = (
            await session.execute(
                select(Capture).where(
                    Capture.paypal_capture_id == payload.capture.paypal_capture_id
                )
            )
        ).scalar_one_or_none()
        if capture_row is None:
            if order_row is None:
                # live disputes may not expose an order id — create a stand-in order
                order_row = Order(
                    merchant_id=merchant.id,
                    paypal_order_id=f"IMPLIED-{payload.paypal_dispute_id}",
                    amount=payload.amount,
                    currency=payload.currency,
                    buyer_label=payload.buyer_label,
                    raw={
                        "tracking": payload.tracking,
                        "shipping": (payload.raw or {}).get("shipping"),
                    },
                )
                session.add(order_row)
                await session.flush()
            capture_row = Capture(
                merchant_id=merchant.id,
                order_id=order_row.id,
                paypal_capture_id=payload.capture.paypal_capture_id,
                status=payload.capture.status,
                amount=payload.capture.amount,
                currency=payload.capture.currency,
                seller_protection_status=payload.capture.seller_protection_status,
                final_capture=True,
                raw={},
            )
            session.add(capture_row)
            await session.flush()

    dispute = (
        await session.execute(
            select(Dispute).where(
                Dispute.merchant_id == merchant.id,
                Dispute.paypal_dispute_id == payload.paypal_dispute_id,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    buyer_hash = payload.buyer_email_hash or (
        pii_hash(payload.order.buyer_email) if payload.order and payload.order.buyer_email else None
    )

    if dispute is None:
        dispute = Dispute(
            merchant_id=merchant.id,
            paypal_dispute_id=payload.paypal_dispute_id,
            paypal_case_number=payload.paypal_case_number,
            order_id=order_row.id if order_row else None,
            capture_id=capture_row.id if capture_row else None,
            buyer_label=payload.buyer_label,
            buyer_email_hash=buyer_hash,
            reason_code=payload.reason_code,
            reason_detail=payload.reason_detail,
            status="RECEIVED",
            paypal_status=payload.paypal_status,
            lifecycle_stage=payload.lifecycle_stage,
            channel="WEBHOOK",
            amount=payload.amount,
            currency=payload.currency,
            response_due_by=payload.response_due_by,
            paypal_created_at=payload.paypal_created_at,
            last_synced_at=now,
            raw=payload.raw,
        )
        session.add(dispute)
        await session.flush()
        session.add(
            DisputeStatusHistory(
                dispute_id=dispute.id,
                from_status=None,
                to_status="RECEIVED",
                actor_type="system",
                reason=f"ingested from {payload.paypal_dispute_id}",
            )
        )
    else:
        if dispute.paypal_status != payload.paypal_status:
            session.add(
                DisputeStatusHistory(
                    dispute_id=dispute.id,
                    from_status=dispute.paypal_status,
                    to_status=payload.paypal_status,
                    actor_type="system",
                    reason="paypal status sync",
                )
            )
        dispute.paypal_status = payload.paypal_status
        dispute.lifecycle_stage = payload.lifecycle_stage
        dispute.last_synced_at = now
        dispute.reason_detail = payload.reason_detail or dispute.reason_detail
        dispute.raw = payload.raw

    for msg in payload.messages:
        key = _dedupe_key(msg.paypal_message_id, msg.body, msg.sent_at)
        exists = (
            await session.execute(
                select(DisputeMessage.id).where(
                    DisputeMessage.dispute_id == dispute.id,
                    DisputeMessage.paypal_message_id == key,
                )
            )
        ).first()
        if exists:
            continue
        session.add(
            DisputeMessage(
                dispute_id=dispute.id,
                direction=msg.direction,
                channel="paypal",
                author_type=msg.author_type,
                body=msg.body,
                paypal_message_id=key,
                sent_at=msg.sent_at,
            )
        )

    await session.commit()
    await session.refresh(dispute)
    return dispute


async def sync_all(session: AsyncSession) -> list[Dispute]:
    from app.paypal.factory import get_adapter

    merchant = await get_or_create_merchant(session)
    adapter = get_adapter()
    payloads = await adapter.list_disputes()
    disputes = [await ingest_dispute(session, merchant, p) for p in payloads]
    logger.info("synced %s disputes (mode=%s)", len(disputes), adapter.mode)
    return disputes
