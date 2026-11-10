"""Replay adapter — deterministic fixtures, zero network.

Any refund produced here is explicitly marked `simulated=True`; the UI must never
present it as a real PayPal refund.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.paypal.base import (
    NormalizedCapture,
    NormalizedDispute,
    NormalizedMessage,
    NormalizedOrder,
    RefundReceipt,
)


def fixtures_dir() -> Path:
    configured = get_settings().fixtures_dir
    if configured:
        return Path(configured)
    here = Path(__file__).resolve()
    for parent in list(here.parents) + [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / "fixtures" / "disputes" / "demo_scenarios.json"
        if candidate.exists():
            return candidate.parent
    raise FileNotFoundError("fixtures/disputes/demo_scenarios.json not found")


def load_fixtures() -> dict[str, Any]:
    path = fixtures_dir() / "demo_scenarios.json"
    return json.loads(path.read_text(encoding="utf-8"))


def parse_dispute(item: dict[str, Any]) -> NormalizedDispute:
    return NormalizedDispute(
        paypal_dispute_id=item["paypal_dispute_id"],
        paypal_case_number=item.get("paypal_case_number"),
        reason_code=item["reason_code"],
        reason_detail=item.get("reason_detail"),
        status=item.get("status", "OPEN"),
        paypal_status=item.get("paypal_status", "OPEN"),
        lifecycle_stage=item.get("lifecycle_stage", "INQUIRY"),
        amount=item["amount"],
        currency=item.get("currency", "USD"),
        response_due_by=item.get("response_due_by"),
        paypal_created_at=item.get("order", {}).get("created_at_paypal"),
        buyer_label=item.get("buyer", {}).get("label"),
        buyer_email_hash=item.get("buyer", {}).get("email_hash"),
        order=NormalizedOrder(**item["order"]) if item.get("order") else None,
        capture=NormalizedCapture(**item["capture"]) if item.get("capture") else None,
        tracking=item.get("tracking"),
        risk_signals=item.get("risk_signals", []),
        messages=[NormalizedMessage(**m) for m in item.get("messages", [])],
        scenario=item.get("scenario"),
        expected_outcome=item.get("expected_outcome"),
        raw=item,
    )


class ReplayAdapter:
    mode = "replay"

    def __init__(self) -> None:
        self._data = load_fixtures()

    def fixtures_version(self) -> str:
        return str(self._data.get("version", "unknown"))

    async def list_disputes(self) -> list[NormalizedDispute]:
        return [parse_dispute(d) for d in self._data.get("disputes", [])]

    async def get_dispute(self, dispute_id: str) -> NormalizedDispute:
        for d in self._data.get("disputes", []):
            if d["paypal_dispute_id"] == dispute_id:
                return parse_dispute(d)
        raise KeyError(f"unknown replay dispute {dispute_id}")

    async def refund(
        self,
        capture_id: str,
        amount,
        currency: str,
        *,
        idempotency_key: str,
        note: str | None = None,
    ) -> RefundReceipt:
        digest = hashlib.sha256(f"{capture_id}:{idempotency_key}".encode()).hexdigest()[:12]
        return RefundReceipt(
            paypal_refund_id=f"REPLAY-RF-{digest.upper()}",
            status="COMPLETED",
            amount=amount,
            currency=currency,
            simulated=True,
            raw={
                "mode": "replay",
                "capture_id": capture_id,
                "note": note,
                "idempotency_key": idempotency_key,
            },
        )

    async def verify_webhook(self, headers: dict[str, str], event: dict[str, Any]) -> bool:
        # Replay mode accepts synthetic events; the delivery row records `signature_valid=False`.
        return True
