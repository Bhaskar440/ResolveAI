"""Live sandbox adapter — real PayPal REST calls.

Read/write surface is intentionally tiny:
  * read:   GET /v1/customer/disputes, GET /v1/customer/disputes/{id}
  * write:  POST /v2/payments/captures/{id}/refund   (only via the executor)
  * verify: POST /v1/notifications/verify-webhook-signature

No agent can reach this class directly; only `execution_service` calls `refund()`.
"""

from __future__ import annotations

import time
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import get_settings
from app.paypal.base import (
    NormalizedCapture,
    NormalizedDispute,
    NormalizedMessage,
    NormalizedOrder,
    PayPalError,
    RefundReceipt,
)

TOKEN_SAFETY_SECONDS = 60


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _money(block: dict[str, Any] | None) -> tuple[Decimal, str]:
    block = block or {}
    value = block.get("value") or block.get("total") or "0"
    return Decimal(str(value)), str(block.get("currency_code") or "USD")


def normalize_dispute(item: dict[str, Any]) -> NormalizedDispute:
    tx = (item.get("disputed_transactions") or [{}])[0]
    amount, currency = _money(tx.get("transaction_amount") or item.get("dispute_amount"))
    buyer_email = (tx.get("buyer") or {}).get("email")
    capture_id = tx.get("seller_transaction_id") or item.get("dispute_id")
    messages = [
        NormalizedMessage(
            direction="inbound" if str(m.get("posted_by", "")).upper() == "BUYER" else "outbound",
            author_type=str(m.get("posted_by", "BUYER")).lower(),
            body=m.get("content") or "",
            sent_at=_dt(m.get("time_posted")),
            paypal_message_id=m.get("message_id"),
        )
        for m in item.get("messages") or []
    ]
    last_buyer_message = next(
        (m.body for m in reversed(messages) if m.direction == "inbound"), None
    )
    return NormalizedDispute(
        paypal_dispute_id=item.get("dispute_id") or item.get("case_number", ""),
        paypal_case_number=item.get("case_number") or item.get("dispute_id"),
        reason_code=item.get("reason") or item.get("reason_code") or "UNKNOWN",
        reason_detail=last_buyer_message,
        status=str(item.get("status") or "OPEN"),
        paypal_status=str(item.get("status") or "OPEN"),
        lifecycle_stage=str(item.get("dispute_life_cycle_stage") or "INQUIRY"),
        amount=amount,
        currency=currency,
        response_due_by=_dt(item.get("seller_response_due_date")),
        paypal_created_at=_dt(item.get("create_time")),
        buyer_label=(buyer_email.split("@")[0][:24] if buyer_email else None),
        buyer_email_hash=None,
        order=NormalizedOrder(
            paypal_order_id=str(tx.get("invoice_number") or item.get("dispute_id")),
            amount=amount,
            currency=currency,
            item_title=tx.get("item_description"),
            buyer_email=buyer_email,
        ),
        capture=NormalizedCapture(
            paypal_capture_id=str(capture_id),
            status=str(tx.get("transaction_status") or "COMPLETED"),
            amount=amount,
            currency=currency,
            seller_protection_status="ELIGIBLE"
            if tx.get("seller_protection_eligible")
            else "UNKNOWN",
            refundable_amount=amount,
        ),
        tracking=None,
        risk_signals=[],
        messages=messages,
        raw=item,
    )


class SandboxAdapter:
    mode = "sandbox"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._token: str | None = None
        self._expires_at = 0.0

    @property
    def _base(self) -> str:
        return self._settings.paypal_base_url.rstrip("/")

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._expires_at - TOKEN_SAFETY_SECONDS:
            return self._token
        res = await client.post(
            f"{self._base}/v1/oauth2/token",
            auth=(self._settings.paypal_client_id, self._settings.paypal_client_secret),
            data={"grant_type": "client_credentials"},
            headers={"Accept": "application/json"},
        )
        if res.status_code != 200:
            raise PayPalError(res.status_code, "OAUTH_FAILED", res.text[:300])
        body = res.json()
        self._token = body["access_token"]
        self._expires_at = time.time() + float(body.get("expires_in", 300))
        return self._token

    async def _request(
        self, method: str, path: str, *, json: dict | None = None, extra: dict | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            token = await self._access_token(client)
            headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
            headers.update(extra or {})
            res = await client.request(method, f"{self._base}{path}", headers=headers, json=json)
            if res.status_code == 401:  # token revoked early — refresh once
                self._token = None
                token = await self._access_token(client)
                headers["Authorization"] = f"Bearer {token}"
                res = await client.request(
                    method, f"{self._base}{path}", headers=headers, json=json
                )
        if res.status_code >= 400:
            try:
                err = res.json()
            except Exception:
                err = {"name": "HTTP_ERROR", "message": res.text[:300]}
            details = err.get("details")
            message = str(err.get("message") or res.text[:300])
            if details:
                message = f"{message} | details={details}"
            raise PayPalError(
                res.status_code,
                str(err.get("name") or "HTTP_ERROR"),
                message,
                err.get("debug_id"),
            )
        return res.json() if res.content else {}

    async def list_disputes(self) -> list[NormalizedDispute]:
        items: list[dict[str, Any]] = []
        page = 1
        page_size = 50
        while page <= 10:
            body = await self._request(
                "GET", f"/v1/customer/disputes?page_size={page_size}&page={page}"
            )
            batch = body.get("items") or []
            items.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return [normalize_dispute(i) for i in items]

    async def get_dispute(self, dispute_id: str) -> NormalizedDispute:
        body = await self._request("GET", f"/v1/customer/disputes/{dispute_id}")
        return normalize_dispute(body)

    async def refund(
        self,
        capture_id: str,
        amount,
        currency: str,
        *,
        idempotency_key: str,
        note: str | None = None,
    ) -> RefundReceipt:
        payload: dict[str, Any] = {
            "amount": {"value": f"{Decimal(amount):.2f}", "currency_code": currency}
        }
        if note:
            payload["note_to_payer"] = note[:255]
        body = await self._request(
            "POST",
            f"/v2/payments/captures/{capture_id}/refund",
            json=payload,
            extra={"PayPal-Request-Id": idempotency_key, "Prefer": "return=representation"},
        )
        return RefundReceipt(
            paypal_refund_id=body.get("id", ""),
            status=body.get("status", "PENDING"),
            amount=Decimal(str((body.get("amount") or {}).get("value", amount))),
            currency=(body.get("amount") or {}).get("currency_code", currency),
            simulated=False,
            raw=body,
        )

    async def verify_webhook(self, headers: dict[str, str], event: dict[str, Any]) -> bool:
        payload = {
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "cert_url": headers.get("paypal-cert-url"),
            "auth_algo": headers.get("paypal-auth-algo"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "webhook_id": self._settings.paypal_webhook_id,
            "webhook_event": event,
        }
        body = await self._request("POST", "/v1/notifications/verify-webhook-signature", json=payload)
        return body.get("verification_status") == "SUCCESS"
