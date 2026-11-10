from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import Dispute, Refund, WebhookDelivery
from app.paypal.base import NormalizedOrder
from app.paypal.factory import get_adapter
from app.paypal.sandbox import normalize_capture, normalize_dispute
from app.services.ingestion import get_or_create_merchant, ingest_dispute
from app.services.payments import persist_order

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("resolveai.webhooks")
settings = get_settings()


async def _process_event(session, event_type: str, event: dict) -> str:
    """Persist the parts of a verified event that belong in PostgreSQL."""
    merchant = await get_or_create_merchant(session)
    resource = event.get("resource") or {}

    if event_type.startswith("CUSTOMER.DISPUTE."):
        payload = normalize_dispute(resource)
        await ingest_dispute(session, merchant, payload)
        return "processed"

    if event_type.startswith(("PAYMENT.CAPTURE.REFUND", "PAYMENT.REFUND.")):
        refund_id = str(resource.get("id") or "")
        if not refund_id:
            return "stored"
        refund = (
            await session.execute(
                select(Refund).where(Refund.paypal_refund_id == refund_id)
            )
        ).scalar_one_or_none()
        if refund is None:
            return "stored"
        refund.status = str(resource.get("status") or refund.status)
        refund.raw = {**refund.raw, "webhook_event": event_type, "webhook_status": refund.status}
        if refund.status == "COMPLETED" and refund.dispute_id is not None:
            dispute = await session.get(Dispute, refund.dispute_id)
            if dispute is not None and dispute.status == "REFUND_PENDING":
                # The refund settled after we accepted it — only now is it resolved.
                dispute.status = "RESOLVED"
                dispute.resolved_at = datetime.now(UTC)
                dispute.recovered_amount = refund.amount
        await session.commit()
        return "processed"

    if event_type.startswith("PAYMENT.CAPTURE."):
        capture = normalize_capture(resource)
        if not capture.paypal_capture_id:
            return "stored"
        related = (resource.get("supplementary_data") or {}).get("related_ids") or {}
        order_id = (
            capture.order_id
            or related.get("order_id")
            or f"EVENT-{capture.paypal_capture_id}"
        )
        order = NormalizedOrder(
            paypal_order_id=str(order_id),
            amount=capture.amount,
            currency=capture.currency,
            status="COMPLETED" if capture.status == "COMPLETED" else "CREATED",
            capture=capture,
            raw=resource,
        )
        await persist_order(session, merchant, order)
        await session.commit()
        return "processed"

    return "stored"


@router.post("/paypal")
async def paypal_webhook(request: Request, session: SessionDep) -> dict:
    raw = await request.body()
    try:
        event = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise AppError("Webhook body is not valid JSON.", status_code=400, code="INVALID_PAYLOAD")

    headers = {k.lower(): v for k, v in request.headers.items()}
    adapter = get_adapter()
    try:
        signature_valid = await adapter.verify_webhook(headers, event)
    except Exception as exc:
        logger.warning("webhook verification failed: %s", exc)
        signature_valid = False

    if settings.paypal_mode == "sandbox" and not signature_valid:
        raise AppError(
            "Webhook signature verification failed.",
            status_code=400,
            code="INVALID_SIGNATURE",
        )

    event_id = str(event.get("id") or uuid4().hex)
    delivery = WebhookDelivery(
        provider="paypal",
        event_id=event_id,
        event_type=str(event.get("event_type") or "UNKNOWN"),
        transmission_id=headers.get("paypal-transmission-id"),
        payload=event,
        signature_valid=signature_valid,
        status="received",
    )
    session.add(delivery)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return {"status": "duplicate", "event_id": event_id}

    # Only sandbox mode performs side effects; replay stores the delivery honestly.
    if settings.paypal_mode == "sandbox":
        try:
            status = await _process_event(session, delivery.event_type, event)
            delivery.status = status
            delivery.processed_at = datetime.now(UTC)
            delivery.last_error = None
            await session.commit()
            return {"status": status, "event_id": event_id, "signature_valid": signature_valid}
        except Exception as exc:
            logger.exception("webhook processing failed")
            delivery.status = "failed"
            delivery.last_error = str(exc)[:800]
            await session.commit()
            return {"status": "failed", "event_id": event_id}

    delivery.status = "stored"
    await session.commit()
    return {"status": delivery.status, "event_id": event_id, "signature_valid": signature_valid}
