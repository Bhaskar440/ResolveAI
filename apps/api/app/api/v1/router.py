from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import disputes, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router, prefix="/system")
api_router.include_router(disputes.router)
