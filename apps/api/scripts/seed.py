"""Seed the demo merchant and ingest the replay fixtures.

Usage (from apps/api):  uv run python -m scripts.seed
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.db.models import Dispute
from app.db.session import SessionLocal
from app.paypal.factory import get_adapter
from app.services.ingestion import get_or_create_merchant, sync_all


async def main() -> None:
    async with SessionLocal() as session:
        merchant = await get_or_create_merchant(session)
        before = (await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
        disputes = await sync_all(session)
        after = (await session.execute(select(func.count()).select_from(Dispute))).scalar_one()
        adapter = get_adapter()
        print(f"merchant: {merchant.slug} ({merchant.id})")
        print(f"mode: {adapter.mode}")
        print(f"disputes ingested: {len(disputes)} (total rows {before} -> {after})")
        for d in disputes:
            print(
                f"  {d.paypal_dispute_id}  {d.reason_code:44} {d.amount} {d.currency} "
                f"due={d.response_due_by} status={d.status}"
            )


if __name__ == "__main__":
    asyncio.run(main())
