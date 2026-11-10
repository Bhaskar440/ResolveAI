from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DBStatus(BaseModel):
    connected: bool
    latency_ms: float
    server_version: str | None = None
    error: str | None = None


class Counts(BaseModel):
    disputes: int = 0
    runs: int = 0
    refunds: int = 0


class SystemStatus(BaseModel):
    status: str = Field(description="ok | degraded")
    app: str
    env: str
    mode: str
    checked_at: datetime
    db: DBStatus
    counts: Counts
    schema_tables: int
    capabilities: dict[str, bool]
    request_id: str


class DisputeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paypal_case_number: str | None = None
    reason_code: str
    status: str
    paypal_status: str
    amount: Decimal
    currency: str
    confidence: Decimal | None = None
    decision_code: str | None = None
    requires_approval: bool
    response_due_by: datetime | None = None
    updated_at: datetime


class DisputeList(BaseModel):
    items: list[DisputeOut]
    total: int
    limit: int
    offset: int
