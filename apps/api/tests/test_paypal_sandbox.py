"""Sandbox adapter wire-contract tests using httpx.MockTransport.

These do not pretend a live PayPal call happened: they assert the exact request
shape (idempotency header, amounts, paths) and the parsing/error behaviour. The
live proof runs through scripts/verify_sandbox_adapter.py with real credentials.
"""

from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.paypal.base import PayPalError
from app.paypal.sandbox import SandboxAdapter

TOKEN = {"access_token": "test-token", "expires_in": 3600}


def _json(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8")) if request.content else {}


def _token_response() -> httpx.Response:
    return httpx.Response(200, json=TOKEN)


def _order_body(status: str = "PAYER_ACTION_REQUIRED", capture: bool = False) -> dict:
    body: dict = {
        "id": "ORDER-1",
        "status": status,
        "purchase_units": [
            {
                "amount": {"value": "40.00", "currency_code": "USD"},
                "description": "Ceramic mug",
                "invoice_id": "INV-1",
            }
        ],
        "links": [{"rel": "payer-action", "href": "https://paypal.test/approve/ORDER-1"}],
    }
    if capture:
        body["purchase_units"][0]["payments"] = {
            "captures": [
                {
                    "id": "CAP-1",
                    "status": "COMPLETED",
                    "amount": {"value": "40.00", "currency_code": "USD"},
                    "final_capture": True,
                    "seller_protection": {"status": "ELIGIBLE"},
                }
            ]
        }
    return body


@pytest.mark.asyncio
async def test_create_order_sends_expected_payload_and_parses_approval_link():
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        seen.append(request)
        return httpx.Response(201, json=_order_body())

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    order = await adapter.create_order(
        amount=Decimal(40),
        currency="USD",
        description="Ceramic mug",
        invoice_id="INV-1",
        return_url="http://localhost:3000/",
        cancel_url="http://localhost:3000/",
        idempotency_key="order-key-1",
    )

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v2/checkout/orders"
    assert request.headers["PayPal-Request-Id"] == "order-key-1"
    payload = _json(request)
    assert payload["intent"] == "CAPTURE"
    assert payload["purchase_units"][0]["amount"] == {
        "currency_code": "USD",
        "value": "40.00",
    }
    assert payload["payment_source"]["paypal"]["experience_context"]["return_url"].endswith("/")

    assert order.paypal_order_id == "ORDER-1"
    assert order.status == "PAYER_ACTION_REQUIRED"
    assert order.amount == Decimal("40.00")
    assert order.approval_url == "https://paypal.test/approve/ORDER-1"
    assert order.simulated is False


@pytest.mark.asyncio
async def test_capture_order_is_idempotent_and_parses_capture():
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        seen.append(request)
        return httpx.Response(201, json=_order_body("COMPLETED", capture=True))

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    order = await adapter.capture_order("ORDER-1", idempotency_key="capture-ORDER-1")

    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == "/v2/checkout/orders/ORDER-1/capture"
    assert request.headers["PayPal-Request-Id"] == "capture-ORDER-1"
    assert order.status == "COMPLETED"
    assert order.capture is not None
    assert order.capture.paypal_capture_id == "CAP-1"
    assert order.capture.status == "COMPLETED"
    assert order.capture.amount == Decimal("40.00")
    assert order.capture.seller_protection_status == "ELIGIBLE"
    assert order.capture.final_capture is True


@pytest.mark.asyncio
async def test_partial_refund_sends_exact_amount_and_note():
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        seen.append(request)
        return httpx.Response(
            201,
            json={
                "id": "REF-1",
                "status": "COMPLETED",
                "amount": {"value": "35.00", "currency_code": "USD"},
            },
        )

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    receipt = await adapter.refund(
        "CAP-1", Decimal(35), "USD", idempotency_key="refund-key-1", note="partial goodwill"
    )

    request = seen[0]
    assert request.url.path == "/v2/payments/captures/CAP-1/refund"
    assert request.headers["PayPal-Request-Id"] == "refund-key-1"
    assert _json(request)["amount"] == {"value": "35.00", "currency_code": "USD"}
    assert _json(request)["note_to_payer"] == "partial goodwill"
    assert receipt.paypal_refund_id == "REF-1"
    assert receipt.amount == Decimal("35.00")
    assert receipt.simulated is False


@pytest.mark.asyncio
async def test_capture_and_refund_reads():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        if request.url.path == "/v2/payments/captures/CAP-1":
            return httpx.Response(
                200,
                json={
                    "id": "CAP-1",
                    "status": "COMPLETED",
                    "amount": {"value": "40.00", "currency_code": "USD"},
                    "final_capture": True,
                },
            )
        if request.url.path == "/v2/payments/refunds/REF-1":
            return httpx.Response(
                200,
                json={
                    "id": "REF-1",
                    "status": "PENDING",
                    "amount": {"value": "40.00", "currency_code": "USD"},
                },
            )
        return httpx.Response(404, json={"name": "RESOURCE_NOT_FOUND"})

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    capture = await adapter.get_capture("CAP-1")
    refund = await adapter.get_refund("REF-1")

    assert capture.paypal_capture_id == "CAP-1"
    assert capture.status == "COMPLETED"
    assert refund.paypal_refund_id == "REF-1"
    assert refund.status == "PENDING"
    assert refund.amount == Decimal("40.00")


@pytest.mark.asyncio
async def test_paypal_error_surfaces_name_message_and_debug_id():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        return httpx.Response(
            422,
            json={
                "name": "ORDER_NOT_APPROVED",
                "message": "The order is not approved by the payer.",
                "debug_id": "dbg-123",
                "details": [{"issue": "ORDER_NOT_APPROVED"}],
            },
        )

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    with pytest.raises(PayPalError) as raised:
        await adapter.capture_order("ORDER-1", idempotency_key="k")

    assert raised.value.status == 422
    assert raised.value.code == "ORDER_NOT_APPROVED"
    assert raised.value.debug_id == "dbg-123"
    assert "not approved" in str(raised.value)


@pytest.mark.asyncio
async def test_webhook_verification_maps_paypal_headers(monkeypatch):
    seen: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return _token_response()
        seen.append(_json(request))
        return httpx.Response(200, json={"verification_status": "SUCCESS"})

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(adapter._settings, "paypal_webhook_id", "WH-TEST")
    event = {"id": "EVT-1", "event_type": "CUSTOMER.DISPUTE.CREATED", "resource": {"id": "D-1"}}
    headers = {
        "paypal-transmission-id": "tid",
        "paypal-transmission-time": "2026-11-10T00:00:00Z",
        "paypal-cert-url": "https://paypal.test/cert",
        "paypal-auth-algo": "SHA256withRSA",
        "paypal-transmission-sig": "sig",
    }

    assert await adapter.verify_webhook(headers, event) is True
    assert seen[0]["webhook_id"] == "WH-TEST"
    assert seen[0]["transmission_id"] == "tid"
    assert seen[0]["transmission_sig"] == "sig"
    assert seen[0]["webhook_event"] == event


@pytest.mark.asyncio
async def test_access_token_is_cached_across_requests():
    token_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls
        if request.url.path == "/v1/oauth2/token":
            token_calls += 1
            return _token_response()
        return httpx.Response(200, json=_order_body())

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    await adapter.get_order("ORDER-1")
    await adapter.get_order("ORDER-1")
    assert token_calls == 1


@pytest.mark.asyncio
async def test_401_refreshes_token_once_and_retries():
    token_calls = 0
    order_calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal token_calls, order_calls
        if request.url.path == "/v1/oauth2/token":
            token_calls += 1
            return httpx.Response(
                200, json={"access_token": f"token-{token_calls}", "expires_in": 3600}
            )
        order_calls += 1
        if order_calls == 1:
            return httpx.Response(401, json={"name": "AUTHENTICATION_FAILURE"})
        return httpx.Response(201, json=_order_body("COMPLETED", capture=True))

    adapter = SandboxAdapter(transport=httpx.MockTransport(handler))
    order = await adapter.capture_order("ORDER-1", idempotency_key="k")

    assert token_calls == 2
    assert order_calls == 2
    assert order.capture is not None
    assert order.capture.paypal_capture_id == "CAP-1"
