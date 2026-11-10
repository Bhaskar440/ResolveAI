"""Run the agents against seeded disputes — the CLI twin of POST /disputes/{id}/run.

Usage:
  uv run python -m scripts.run_demo                 # run every non-resolved dispute
  uv run python -m scripts.run_demo PP-D-91001      # run one
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.db.models import AgentStep, Decision, Dispute, Refund
from app.db.session import SessionLocal
from app.services.orchestrator import run_dispute


async def main(target: str | None) -> None:
    async with SessionLocal() as session:
        stmt = select(Dispute).order_by(Dispute.paypal_dispute_id)
        if target:
            stmt = stmt.where(Dispute.paypal_dispute_id == target)
        disputes = (await session.execute(stmt)).scalars().all()
        for dispute in disputes:
            if dispute.status == "RESOLVED":
                print(f"skip {dispute.paypal_dispute_id}: already resolved")
                continue
            print(f"\n=== {dispute.paypal_dispute_id} {dispute.reason_code} {dispute.amount} {dispute.currency}")
            try:
                run = await run_dispute(session, dispute.id, trigger="cli")
            except Exception as exc:
                print(f"  FAILED: {type(exc).__name__}: {exc}")
                continue

            steps = (
                (
                    await session.execute(
                        select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.seq)
                    )
                )
                .scalars()
                .all()
            )
            for step in steps:
                model = f" [{step.tokens} tok]" if step.tokens else ""
                print(f"  {step.seq:02d} {step.agent:11} {step.step_type:9} {step.summary}{model}")

            decision = (
                await session.execute(select(Decision).where(Decision.run_id == run.id))
            ).scalar_one_or_none()
            refund = (
                await session.execute(select(Refund).where(Refund.dispute_id == dispute.id))
            ).scalars().first()
            await session.refresh(dispute)
            print(
                f"  -> run={run.status} dispute={dispute.status} decision="
                f"{decision.decision_code if decision else None} amount={decision.amount if decision else 0} "
                f"approval={decision.requires_approval if decision else None}"
            )
            if refund:
                print(
                    f"  -> refund {refund.paypal_refund_id} {refund.amount} {refund.currency} "
                    f"status={refund.status} simulated={refund.raw.get('simulated')}"
                )


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
