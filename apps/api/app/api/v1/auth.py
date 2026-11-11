"""Real merchant login/session endpoints.

The browser receives an HttpOnly, signed cookie. Passwords are stored as scrypt
hashes in ``merchant_users``; there is no frontend-only demo auth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select

from app.api.deps import SessionDep
from app.core.auth import create_session_token, decode_session_token
from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.db.models import Merchant, MerchantUser
from app.schemas.responses import LoginRequest, SessionOut, SessionUser
from app.services.auth import authenticate, ensure_demo_user

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _session_payload(user: MerchantUser, merchant: Merchant, expires_at) -> SessionOut:
    return SessionOut(
        user=SessionUser(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
            merchant_id=merchant.id,
            merchant_name=merchant.name,
            merchant_slug=merchant.slug,
        ),
        expires_at=expires_at,
        mode=settings.paypal_mode,
    )


@router.post("/login", response_model=SessionOut)
async def login(body: LoginRequest, response: Response, session: SessionDep) -> SessionOut:
    await ensure_demo_user(session)
    result = await authenticate(session, body.email, body.password)
    if result is None:
        raise UnauthorizedError("Incorrect email or password.")
    user, merchant = result
    token, expires_at = create_session_token(user.id, merchant.id)
    await session.commit()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=int((expires_at - datetime.now(UTC)).total_seconds()),
        httponly=True,
        secure=settings.auth_cookie_secure or settings.app_env == "production",
        samesite=settings.auth_cookie_samesite.lower(),
        path="/",
    )
    return _session_payload(user, merchant, expires_at)


@router.get("/session", response_model=SessionOut)
async def session_info(request: Request, session: SessionDep) -> SessionOut:
    token = request.cookies.get(settings.auth_cookie_name)
    if not token:
        raise UnauthorizedError("No active session.")
    try:
        claims = decode_session_token(token)
        user_id = UUID(str(claims["sub"]))
        merchant_id = UUID(str(claims["merchant_id"]))
    except (ValueError, KeyError, TypeError):
        raise UnauthorizedError("Your session has expired. Sign in again.") from None

    row = (
        await session.execute(
            select(MerchantUser, Merchant)
            .join(Merchant, Merchant.id == MerchantUser.merchant_id)
            .where(
                MerchantUser.id == user_id,
                MerchantUser.merchant_id == merchant_id,
                MerchantUser.is_active.is_(True),
            )
        )
    ).first()
    if row is None:
        raise UnauthorizedError("Your session is no longer valid. Sign in again.")
    user, merchant = row
    expires_at = datetime.fromtimestamp(int(claims["exp"]), tz=UTC)
    return _session_payload(user, merchant, expires_at)


@router.post("/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(
        settings.auth_cookie_name,
        path="/",
        httponly=True,
        samesite=settings.auth_cookie_samesite.lower(),
        secure=settings.auth_cookie_secure or settings.app_env == "production",
    )
    return {"status": "signed_out"}
