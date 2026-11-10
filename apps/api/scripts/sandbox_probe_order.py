"""Create one $1 sandbox order through the app's payment service (no capture).

    PAYPAL_MODE=sandbox uv run python -m scripts.sandbox_probe_order

Proves the live create-order + PostgreSQL persistence path used by the API. It does
not capture and does not move money. The printed link can be approved later; the id
is appended to var/sandbox_orders.json so capture_sandbox_orders can pick it up.
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
STORE = ROOT / "var" / "sandbox_orders.json"


async def main() -> None:
    settings = get_settings()
    if settings.paypal_mode != "sandbox":
        print("refusing: set PAYPAL_MODE=sandbox")
        return

    invoice = f"PROBE-{int(time.time())}"
    async with SessionLocal() as session:
        try:
            _, order = await payments.create_checkout_order(
                session,
                amount=Decimal("1.00"),
                currency="USD",
                description="ResolveAI integration probe",
                invoice_id=invoice,
                return_url=f"{settings.web_base_url}/",
                cancel_url=f"{settings.web_base_url}/",
            )
        except PayPalError as exc:
            print(f"FAILED {exc.status} {exc.code}: {exc}")
            return

    record = {
        "invoice_id": invoice,
        "amount": "1.00",
        "description": "ResolveAI integration probe",
        "order_id": order.paypal_order_id,
        "status": order.status,
        "payer_action_url": order.approval_url,
        "stored_in_postgres": True,
    }
    data = {"created_at": time.time(), "orders": []}
    if STORE.exists():
        data = json.loads(STORE.read_text("utf-8"))
    data.setdefault("orders", []).append(record)
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), "utf-8")

    print(f"order={order.paypal_order_id} status={order.status} stored=yes")
    print(f"approval_url={order.approval_url}")
    print(f"appended to {STORE}")


if __name__ == "__main__":
    asyncio.run(main())
