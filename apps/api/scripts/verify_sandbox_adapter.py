"""Read-only proof that the sandbox adapter works with the real PayPal API.

    PAYPAL_MODE=sandbox uv run python -m scripts.verify_sandbox_adapter

It never calls a write endpoint. It prints counts and masked ids only.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.paypal.factory import get_adapter  # noqa: E402
from app.paypal.replay import ReplayAdapter  # noqa: E402


async def main() -> None:
    settings = get_settings()
    adapter = get_adapter()
    print(f"mode: {adapter.mode}")
    print(f"base_url: {settings.paypal_base_url}")
    if isinstance(adapter, ReplayAdapter):
        print("refusing: PAYPAL_MODE is replay (no live call made)")
        return

    disputes = await adapter.list_disputes()
    print(f"live disputes visible to this app: {len(disputes)}")
    for d in disputes[:10]:
        masked = d.paypal_dispute_id[:6] + "..." if d.paypal_dispute_id else "?"
        print(
            f"  {masked}  {d.reason_code:44} {d.amount} {d.currency} "
            f"status={d.paypal_status} stage={d.lifecycle_stage}"
        )
    print("OK: authenticated read path works through the app adapter")


if __name__ == "__main__":
    asyncio.run(main())
