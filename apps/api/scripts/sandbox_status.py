"""Read-only status of the sandbox orders and their PostgreSQL rows.

    PAYPAL_MODE=sandbox uv run python -m scripts.sandbox_status

Never writes to PayPal or the database. Shows the order status PayPal reports, the
payer approval state, the capture id (if any), and whether order/capture rows exist
in PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.models import Capture, Order
from app.db.session import SessionLocal
from app.paypal.base import PayPalError
from app.paypal.factory import get_adapter

STORE = Path(__file__).resolve().parents[3] / "var" / "sandbox_orders.json"


async def main() -> None:
    if not STORE.exists():
        print("no var/sandbox_orders.json")
        return
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        print("refusing: set PAYPAL_MODE=sandbox to query live order status")
        return

    data = json.loads(STORE.read_text("utf-8"))
    adapter = get_adapter()
    print(f"mode: {adapter.mode}  environment: {settings.paypal_base_url}")

    async with SessionLocal() as session:
        for item in data["orders"]:
            try:
                order = await adapter.get_order(item["order_id"])
            except PayPalError as exc:
                print(f"{item['invoice_id']} GET FAILED {exc.status} {exc.code}: {exc}")
                continue

            order_row = (
                await session.execute(
                    select(Order).where(Order.paypal_order_id == item["order_id"])
                )
            ).scalar_one_or_none()
            capture_row = None
            capture = order.capture
            if item.get("capture_id"):
                capture_row = (
                    await session.execute(
                        select(Capture).where(
                            Capture.paypal_capture_id == item["capture_id"]
                        )
                    )
                ).scalar_one_or_none()
                try:
                    capture = await adapter.get_capture(item["capture_id"])
                except PayPalError as exc:
                    print(f"  capture GET FAILED {exc.status} {exc.code}: {exc}")

            payment_source = (order.raw.get("payment_source") or {}).get("paypal") or {}
            print(
                f"{item['invoice_id']}  {item['amount']} USD  status={order.status}  "
                f"payer={payment_source.get('email_address') or 'not approved'}  "
                f"capture={(capture.paypal_capture_id if capture else '-')}"
                f"/{capture.status if capture else '-'}  "
                f"db_order={'yes' if order_row else 'no'}  "
                f"db_capture={'yes' if capture_row else 'no'}"
            )


if __name__ == "__main__":
    asyncio.run(main())
