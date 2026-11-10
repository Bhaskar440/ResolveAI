from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def session_scope() -> AsyncIterator[AsyncSession]:  # pragma: no cover - alias
    async for s in get_session():
        yield s
