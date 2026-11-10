from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Request
from sqlalchemy.exc import IntegrityError

from app.api.deps import SessionDep
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import WebhookDelivery
from app.paypal.factory import get_adapter
from app.paypal.sandbox import normalize_dispute
from app.services.ingestion import get_or_create_merchant, ingest_dispute

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger("resolveai.webhooks")
settings = get_settings()


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

    if delivery.event_type.startswith("CUSTOMER.DISPUTE.") and settings.paypal_mode == "sandbox":
        try:
            payload = normalize_dispute(event.get("resource") or {})
            merchant = await get_or_create_merchant(session)
            dispute = await ingest_dispute(session, merchant, payload)
            delivery.status = "processed"
            delivery.processed_at = datetime.now(UTC)
            delivery.last_error = None
            await session.commit()
            return {
                "status": "processed",
                "event_id": event_id,
                "dispute_id": str(dispute.id),
            }
        except Exception as exc:
            logger.exception("webhook processing failed")
            delivery.status = "failed"
            delivery.last_error = str(exc)[:800]
            await session.commit()
            return {"status": "failed", "event_id": event_id}
    else:
        delivery.status = "stored"
        await session.commit()

    return {"status": delivery.status, "event_id": event_id, "signature_valid": signature_valid}
