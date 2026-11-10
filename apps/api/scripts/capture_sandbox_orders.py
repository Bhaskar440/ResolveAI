"""Capture approved sandbox orders and persist the captures in PostgreSQL.

    uv run python -m scripts.capture_sandbox_orders

Reads var/sandbox_orders.json, asks PayPal for each order status, captures only the
APPROVED ones, and stores order + capture rows in PostgreSQL. Safe to re-run:
already-captured orders are read back instead of captured again.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.paypal.base import PayPalError
from app.services import payments

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "var" / "sandbox_orders.json"


async def main() -> None:
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        print("refusing: set PAYPAL_MODE=sandbox to capture live sandbox orders")
        return
    if not STORE.exists():
        print("no var/sandbox_orders.json - run scripts.create_sandbox_orders first")
        return
    data = json.loads(STORE.read_text("utf-8"))
    print(f"environment: {settings.paypal_base_url}")

    async with SessionLocal() as session:
        for order in data["orders"]:
            if order.get("capture_id"):
                print(f"{order['invoice_id']} already captured: {order['capture_id']}")
                continue

            try:
                _, remote = await payments.capture_approved_order(
                    session, paypal_order_id=order["order_id"]
                )
            except payments.OrderNotApprovedError as exc:
                await session.rollback()
                print(f"{order['invoice_id']} not ready: {exc}")
                continue
            except payments.PaymentStateError as exc:
                await session.rollback()
                print(f"{order['invoice_id']} capture FAILED: {exc}")
                continue
            except PayPalError as exc:
                await session.rollback()
                print(f"{order['invoice_id']} capture FAILED {exc.status} {exc.code}: {exc}")
                continue

            capture = remote.capture
            if capture is None:
                print(f"{order['invoice_id']} captured but PayPal returned no capture id")
                continue
            order.update(
                {
                    "status": remote.status,
                    "capture_id": capture.paypal_capture_id,
                    "capture_status": capture.status,
                    "capture_amount": str(capture.amount),
                    "capture_currency": capture.currency,
                    "capture_simulated": capture.simulated,
                }
            )
            print(
                f"{order['invoice_id']}  {order['amount']} USD  order={order['order_id']}  "
                f"capture={capture.paypal_capture_id} status={capture.status}  stored=yes"
            )

    STORE.write_text(json.dumps(data, indent=2), "utf-8")
    missing = [o["invoice_id"] for o in data["orders"] if not o.get("capture_id")]
    if missing:
        print(f"\nnot captured yet: {', '.join(missing)} - approve the buyer links first")
    else:
        print("\nall orders captured. Order + capture rows are in PostgreSQL.")


if __name__ == "__main__":
    asyncio.run(main())
