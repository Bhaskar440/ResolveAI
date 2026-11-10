"""Hash-chained audit log: every state change is append-only and verifiable."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def append_audit(
    session: AsyncSession,
    *,
    merchant_id: UUID | None,
    actor_type: str,
    action: str,
    entity_type: str,
    entity_id: str,
    actor_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditLog:
    prev = (
        await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    ).scalar_one_or_none()
    prev_hash = prev.hash if prev else "genesis"
    body = json.dumps(
        {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "before": before or {},
            "after": after or {},
            "ts": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    digest = hashlib.sha256(f"{prev_hash}:{body}".encode()).hexdigest()
    row = AuditLog(
        merchant_id=merchant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        prev_hash=prev_hash,
        hash=digest,
    )
    session.add(row)
    await session.flush()
    return row
