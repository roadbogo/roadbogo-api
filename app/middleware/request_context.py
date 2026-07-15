import logging
import time
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.exceptions import ERROR_MESSAGES
from app.core.responses import error_response

logger = logging.getLogger("roadbogo.requests")

MAX_CONTEXT_HEADER_LENGTH = 128


def normalize_context_id(value: str | None) -> str:
    if value is None:
        return str(uuid4())
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_CONTEXT_HEADER_LENGTH:
        return str(uuid4())
    return cleaned


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = normalize_context_id(request.headers.get("X-Request-ID"))
        trace_id = normalize_context_id(request.headers.get("X-Trace-ID"))
        request.state.request_id = request_id
        request.state.trace_id = trace_id

        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            logger.exception(
                "Unhandled exception request_id=%s trace_id=%s",
                request_id,
                trace_id,
            )
            code, message = ERROR_MESSAGES[500]
            response = JSONResponse(
                status_code=500,
                content=error_response(
                    code=code,
                    message=message,
                    trace_id=trace_id,
                ),
            )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            "request_id=%s trace_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
            request_id,
            trace_id,
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )
        return response
