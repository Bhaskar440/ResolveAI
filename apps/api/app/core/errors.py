"""Error envelope + exception handlers.

Every failure returns the same shape, so the frontend never has to guess:

    {"error": {"code": "...", "message": "...", "details": {...},
               "request_id": "...", "retryable": false}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx

logger = logging.getLogger("resolveai.errors")


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    retryable = False
    message = "Something went wrong."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if status_code:
            self.status_code = status_code
        if code:
            self.code = code
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found."


class ConflictError(AppError):
    status_code = 409
    code = "STATE_CONFLICT"
    message = "The resource is not in a state that allows this action."


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    message = "Sign in to continue."


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Request validation failed."


class PolicyDeniedError(AppError):
    status_code = 403
    code = "POLICY_DENIED"
    message = "Policy does not allow this action."


class DependencyUnavailableError(AppError):
    status_code = 503
    code = "DEPENDENCY_UNAVAILABLE"
    retryable = True
    message = "A downstream dependency is unavailable."


def _payload(code: str, message: str, details: dict[str, Any], retryable: bool) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id_ctx.get(),
            "retryable": retryable,
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        logger.warning("%s %s -> %s: %s", request.method, request.url.path, exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(exc.code, exc.message, exc.details, exc.retryable),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail), {}, False),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_payload(
                "VALIDATION_ERROR",
                "Request validation failed.",
                {"fields": exc.errors()[:10]},
                False,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_payload("INTERNAL_ERROR", "An unexpected error occurred.", {}, False),
        )
