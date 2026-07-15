from typing import Any


def success_response(
    data: Any = None,
    message: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "message": message,
        "trace_id": trace_id,
    }


def error_response(
    code: str,
    message: str,
    trace_id: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "trace_id": trace_id,
    }
