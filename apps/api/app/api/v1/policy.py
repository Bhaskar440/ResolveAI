from __future__ import annotations

from fastapi import APIRouter

from app.agents.policy.engine import load_rules

router = APIRouter(prefix="/policy", tags=["policy"])


@router.get("/rules")
async def rules() -> dict:
    """The exact ruleset the gate is using right now — no UI duplication."""
    return load_rules()
