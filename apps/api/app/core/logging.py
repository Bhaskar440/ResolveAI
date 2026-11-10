"""Structured logging with request correlation."""

from __future__ import annotations

import contextvars
import logging
import sys

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = request_id_ctx.get()
        return True


FORMAT = "%(asctime)s %(levelname)-7s %(name)-28s [%(request_id)s] %(message)s"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FORMAT, datefmt="%Y-%m-%dT%H:%M:%S%z"))
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # keep uvicorn's access log, but route it through the same handler
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.addHandler(handler)
        lg.propagate = False
