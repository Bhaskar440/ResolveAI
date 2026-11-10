"""Request id + timing middleware."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx

HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get(HEADER) or uuid.uuid4().hex[:16]
        token = request_id_ctx.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers[HEADER] = rid
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
        return response
