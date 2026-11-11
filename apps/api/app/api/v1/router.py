from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    approvals,
    auth,
    complaints,
    demo,
    disputes,
    knowledge,
    metrics,
    payments,
    policy,
    runs,
    system,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(system.router, prefix="/system")
api_router.include_router(complaints.router)
api_router.include_router(policy.router)
api_router.include_router(disputes.router)
api_router.include_router(runs.router)
api_router.include_router(approvals.router)
api_router.include_router(metrics.router)
api_router.include_router(payments.router)
api_router.include_router(webhooks.router)
api_router.include_router(knowledge.router)
api_router.include_router(demo.router)
