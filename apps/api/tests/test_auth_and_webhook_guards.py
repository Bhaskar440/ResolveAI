"""Route-boundary guards: session required for mutations, webhook authenticity."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.api.deps import require_session
from app.api.v1 import webhooks
from app.core.auth import create_session_token
from app.core.config import get_settings
from app.core.errors import AppError, UnauthorizedError


class _Request:
    def __init__(self, payload: dict | None = None) -> None:
        self._payload = payload or {}
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _Adapter:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    async def verify_webhook(self, headers, event) -> bool:
        return self.valid


@pytest.mark.asyncio
async def test_mutating_routes_reject_missing_session_cookie():
    with pytest.raises(UnauthorizedError):
        await require_session(SimpleNamespace(cookies={}), None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mutating_routes_reject_forged_session_cookie():
    request = SimpleNamespace(cookies={get_settings().auth_cookie_name: "forged.token"})
    with pytest.raises(UnauthorizedError):
        await require_session(request, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mutating_routes_reject_expired_session_cookie():
    token, _ = create_session_token(uuid4(), uuid4(), ttl_hours=-1)
    request = SimpleNamespace(cookies={get_settings().auth_cookie_name: token})
    with pytest.raises(UnauthorizedError):
        await require_session(request, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_webhook_rejects_malformed_json_before_side_effects():
    request = SimpleNamespace(
        headers={},
        body=lambda: _raw(b"{"),
    )
    with pytest.raises(AppError) as exc:
        await webhooks.paypal_webhook(request, None)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert exc.value.code == "INVALID_PAYLOAD"


async def _raw(value: bytes) -> bytes:
    return value


@pytest.mark.asyncio
async def test_sandbox_webhook_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr(webhooks.settings, "paypal_mode", "sandbox")
    monkeypatch.setattr(webhooks, "get_adapter", lambda: _Adapter(False))
    with pytest.raises(AppError) as exc:
        await webhooks.paypal_webhook(_Request({"id": "WH-TEST"}), None)  # type: ignore[arg-type]
    assert exc.value.status_code == 400
    assert exc.value.code == "INVALID_SIGNATURE"
