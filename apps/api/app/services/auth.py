"""Merchant authentication backed by the ``merchant_users`` table."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password, verify_password
from app.core.config import get_settings
from app.db.models import Merchant, MerchantUser
from app.services.ingestion import get_or_create_merchant


async def ensure_demo_user(session: AsyncSession) -> MerchantUser:
    """Create the documented demo account once; never overwrite a real user."""
    settings = get_settings()
    merchant = await get_or_create_merchant(session)
    email = settings.demo_user_email.strip().lower()
    user = (
        await session.execute(
            select(MerchantUser).where(func.lower(MerchantUser.email) == email)
        )
    ).scalar_one_or_none()
    if user is None:
        user = MerchantUser(
            merchant_id=merchant.id,
            email=email,
            password_hash=hash_password(settings.demo_user_password),
            display_name=settings.demo_user_name,
            role=settings.demo_user_role,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    return user


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> tuple[MerchantUser, Merchant] | None:
    normalized = email.strip().lower()
    row = (
        await session.execute(
            select(MerchantUser, Merchant)
            .join(Merchant, Merchant.id == MerchantUser.merchant_id)
            .where(func.lower(MerchantUser.email) == normalized)
        )
    ).first()
    if row is None:
        return None
    user, merchant = row
    if not user.is_active or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(UTC)
    return user, merchant
