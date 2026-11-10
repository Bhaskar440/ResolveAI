from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.paypal.base import PayPalAdapter
from app.paypal.replay import ReplayAdapter
from app.paypal.sandbox import SandboxAdapter


@lru_cache(maxsize=2)
def get_adapter() -> PayPalAdapter:
    settings = get_settings()
    if settings.paypal_mode == "sandbox":
        if not settings.paypal_configured:
            raise RuntimeError("PAYPAL_MODE=sandbox but PAYPAL_CLIENT_ID/SECRET are missing")
        return SandboxAdapter()
    return ReplayAdapter()
