"""Read-only proof that the sandbox adapter works with the real PayPal API.

    PAYPAL_MODE=sandbox uv run python -m scripts.verify_sandbox_adapter

It never calls a write endpoint. It prints counts, masked ids, order statuses, and
capture statuses. This is the honest live check for OAuth + order/capture reads;
captures and refunds are proven by the capture/refund scripts.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.paypal.base import PayPalError
from app.paypal.factory import get_adapter
from app.paypal.replay import ReplayAdapter

ROOT = Path(__file__).resolve().parents[3]
STORE = ROOT / "var" / "sandbox_orders.json"


def _mask(value: str) -> str:
    return f"{value[:6]}...{value[-4:]}" if len(value) > 12 else value


async def main() -> None:
    settings = get_settings()
    adapter = get_adapter()
    print(f"mode: {adapter.mode}")
    print(f"base_url: {settings.paypal_base_url}")
    if isinstance(adapter, ReplayAdapter):
        print("refusing: PAYPAL_MODE is replay (no live call made)")
        return

    print(f"oauth: configured={settings.paypal_configured}")
    disputes = await adapter.list_disputes()
    print(f"live disputes visible to this app: {len(disputes)}")
    for d in disputes[:10]:
        print(
            f"  {_mask(d.paypal_dispute_id):<16} {d.reason_code:44} {d.amount} {d.currency} "
            f"status={d.paypal_status} stage={d.lifecycle_stage}"
        )

    if STORE.exists():
        data = json.loads(STORE.read_text("utf-8"))
        print(f"\norders recorded in {STORE.name}: {len(data.get('orders', []))}")
        for item in data.get("orders", []):
            try:
                order = await adapter.get_order(item["order_id"])
            except PayPalError as exc:
                print(f"  {item['invoice_id']} GET FAILED {exc.status} {exc.code}: {exc}")
                continue
            payer = (order.raw.get("payment_source") or {}).get("paypal") or {}
            print(
                f"  {item['invoice_id']}  order={_mask(order.paypal_order_id):<18} "
                f"status={order.status:<22} payer={payer.get('email_address') or 'not approved'}"
            )
            capture_id = item.get("capture_id")
            if capture_id:
                try:
                    capture = await adapter.get_capture(capture_id)
                except PayPalError as exc:
                    print(f"    capture GET FAILED {exc.status} {exc.code}: {exc}")
                    continue
                print(
                    f"    capture={_mask(capture.paypal_capture_id):<18} "
                    f"status={capture.status} amount={capture.amount} {capture.currency}"
                )
    else:
        print("\nno var/sandbox_orders.json — no orders to check")

    print(
        "\nwebhook: "
        + ("id configured (signature verification can run)" if settings.paypal_webhook_id
           else "NOT CONFIGURED (register a webhook to get PAYPAL_WEBHOOK_ID)")
    )
    print("OK: authenticated read path works through the app adapter; no writes made")


if __name__ == "__main__":
    asyncio.run(main())
