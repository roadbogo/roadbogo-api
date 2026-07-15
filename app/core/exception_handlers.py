from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import ERROR_MESSAGES, UNKNOWN_HTTP_ERROR, AppException
from app.core.responses import error_response


def get_trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", ""))


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=error_response(
            code=code,
            message=message,
            details=details,
            trace_id=trace_id,
        ),
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return build_error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
        trace_id=get_trace_id(request),
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    code, message = ERROR_MESSAGES.get(exc.status_code, UNKNOWN_HTTP_ERROR)
    return build_error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        trace_id=get_trace_id(request),
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    fields = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "reason": str(error["msg"]),
        }
        for error in exc.errors()
    ]
    code, message = ERROR_MESSAGES[422]
    return build_error_response(
        status_code=422,
        code=code,
        message=message,
        details={"fields": fields},
        trace_id=get_trace_id(request),
    )
