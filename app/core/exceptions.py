from typing import Any


class AppException(Exception):
    def __init__(
        self,
        status_code: int = 400,
        code: str = "COMMON_BAD_REQUEST",
        message: str = "잘못된 요청입니다.",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


class DomainException(AppException):
    pass


ERROR_MESSAGES: dict[int, tuple[str, str]] = {
    400: ("COMMON_BAD_REQUEST", "잘못된 요청입니다."),
    401: ("COMMON_UNAUTHORIZED", "인증이 필요합니다."),
    403: ("COMMON_FORBIDDEN", "접근 권한이 없습니다."),
    404: ("COMMON_RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."),
    405: ("COMMON_METHOD_NOT_ALLOWED", "허용되지 않은 HTTP 메서드입니다."),
    422: ("COMMON_VALIDATION_ERROR", "요청값을 확인해 주세요."),
    500: ("COMMON_INTERNAL_ERROR", "서버 처리 중 오류가 발생했습니다."),
}

UNKNOWN_HTTP_ERROR = ("COMMON_HTTP_ERROR", "HTTP 오류가 발생했습니다.")
