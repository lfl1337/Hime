"""
Audit logging middleware.

Logs every inbound HTTP request to a local file in JSON-lines format:

    {"ts": "2026-03-20T12:34:56.789Z", "method": "POST", "path": "/api/v1/texts/",
     "status": 201, "duration_ms": 12.4, "client": "127.0.0.1"}

The log is append-only and never sent anywhere outside the machine.
"""
import json
import logging
import time
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


def _build_logger(log_path: str) -> logging.Logger:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("hime.audit")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Don't bubble up to the root logger

    if not logger.handlers:
        handler = logging.FileHandler(path, encoding="utf-8")
        # Plain format — the JSON payload carries all structure
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    return logger


class AuditMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, log_path: str = "logs/audit.log") -> None:
        super().__init__(app)
        self._logger = _build_logger(log_path)

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": duration_ms,
            "client": request.client.host if request.client else "unknown",
        }
        self._logger.info(json.dumps(record, ensure_ascii=False))

        return response
