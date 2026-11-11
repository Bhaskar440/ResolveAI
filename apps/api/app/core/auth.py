"""Password hashing and signed, stateless session tokens.

The session cookie is HttpOnly and signed with ``SECRET_KEY``. No password or
token is ever logged. The demo password is seeded only when the demo user does
not exist; an existing user is never overwritten.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.config import get_settings

_SCRYPT_N = 16_384
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_DKLEN,
    )
    return (
        f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{_b64encode(salt)}${_b64encode(digest)}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = _b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _session_key() -> bytes:
    settings = get_settings()
    # The application refuses to start without secrets in production; the
    # fallback keeps local replay usable without silently accepting prod tokens.
    return (settings.secret_key or "resolveai-local-session-key").encode("utf-8")


def create_session_token(
    user_id: UUID,
    merchant_id: UUID,
    *,
    ttl_hours: int | None = None,
) -> tuple[str, datetime]:
    settings = get_settings()
    issued = datetime.now(UTC)
    expires = issued + timedelta(hours=ttl_hours or settings.auth_session_hours)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "merchant_id": str(merchant_id),
        "iat": int(issued.timestamp()),
        "exp": int(expires.timestamp()),
    }
    body = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = _b64encode(hmac.new(_session_key(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}", expires


def decode_session_token(token: str) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
        expected = _b64encode(
            hmac.new(_session_key(), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64decode(body))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid session token") from exc
    if not isinstance(payload, dict):
        raise TypeError("invalid session payload")
    expires = payload.get("exp")
    if not isinstance(expires, int) or expires < int(time.time()):
        raise ValueError("session expired")
    if not payload.get("sub") or not payload.get("merchant_id"):
        raise ValueError("session missing subject")
    return payload
