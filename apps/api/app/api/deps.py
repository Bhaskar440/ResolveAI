from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import decode_session_token
from app.core.config import get_settings
from app.core.errors import UnauthorizedError
from app.db.models import Merchant, MerchantUser
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def require_session(request: Request, session: SessionDep) -> MerchantUser:
    """Resolve the signed merchant session cookie or reject the request.

    Mutating merchant routes depend on this guard. Read-only dashboard routes stay
    open so server-rendered pages can hydrate without forwarding the browser cookie.
    """
    token = request.cookies.get(get_settings().auth_cookie_name)
    if not token:
        raise UnauthorizedError("Sign in to continue.")
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
    user, _merchant = row
    return user


CurrentUserDep = Annotated[MerchantUser, Depends(require_session)]


async def session_scope() -> AsyncIterator[AsyncSession]:  # pragma: no cover - alias
    async for s in get_session():
        yield s
