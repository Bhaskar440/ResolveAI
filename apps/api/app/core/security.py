from __future__ import annotations

import hashlib
import hmac

from app.core.config import get_settings


def pii_hash(value: str) -> str:
    """Salted hash for buyer identifiers. Never store the raw email."""
    pepper = get_settings().pii_hash_pepper or "dev-pepper-not-for-production"
    return hashlib.sha256(f"{pepper}:{value.strip().lower()}".encode()).hexdigest()[:16]


def sign_plan(payload: dict) -> str:
    """HMAC over a canonical JSON payload — the executor verifies before moving money."""
    import json

    key = (get_settings().plan_signing_key or "dev-plan-key").encode()
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(key, canonical.encode(), hashlib.sha256).hexdigest()
