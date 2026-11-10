"""Create real sandbox orders through the app's payment service.

    uv run python -m scripts.create_sandbox_orders

Creates three Orders v2 checkouts (40 / 140 / 260 USD) and stores each order row in
PostgreSQL. Prints the payer-action links; the personal sandbox buyer approves each
one in a browser, then `capture_sandbox_orders` captures them and stores captures.

Writes ids/links to var/sandbox_orders.json (git-ignored). No secrets are printed.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.paypal.base import PayPalError
from app.services import payments

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "var" / "sandbox_orders.json"

ORDERS = [
    ("40.00", "Ceramic pour-over set", "INV-91001"),
    ("140.00", "Stoneware dinner set, 12 pieces", "INV-91002"),
    ("260.00", "Wireless noise-cancelling headphones", "INV-91003"),
]


async def main() -> None:
    settings = get_settings()
    if not settings.paypal_configured:
        print("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET missing")
        return
    if settings.paypal_mode != "sandbox":
        print("refusing: set PAYPAL_MODE=sandbox to create live sandbox orders")
        return

    print(f"environment: {settings.paypal_base_url}")
    created: list[dict] = []

    async with SessionLocal() as session:
        for value, description, invoice in ORDERS:
            try:
                _, order = await payments.create_checkout_order(
                    session,
                    amount=Decimal(value),
                    currency="USD",
                    description=description,
                    invoice_id=invoice,
                    return_url=f"{settings.web_base_url}/",
                    cancel_url=f"{settings.web_base_url}/",
                )
            except PayPalError as exc:
                await session.rollback()
                print(f"{invoice} FAILED {exc.status} {exc.code}: {exc}")
                continue

            created.append(
                {
                    "invoice_id": invoice,
                    "amount": value,
                    "description": description,
                    "order_id": order.paypal_order_id,
                    "status": order.status,
                    "payer_action_url": order.approval_url,
                    "stored_in_postgres": True,
                }
            )
            print(
                f"{invoice} {value:>7} USD  order={order.paypal_order_id}  "
                f"status={order.status}  stored=yes"
            )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"created_at": time.time(), "orders": created}, indent=2), "utf-8")
    print(f"\nsaved {len(created)} orders to {OUT}")

    print("\n--- buyer approval links (open each, log in as the PERSONAL sandbox buyer) ---")
    for order in created:
        print(f"\n{order['invoice_id']}  {order['amount']} USD  {order['description']}")
        print(order["payer_action_url"])


if __name__ == "__main__":
    asyncio.run(main())
