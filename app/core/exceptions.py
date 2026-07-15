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
    404: ("COMMON_RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."),
    422: ("COMMON_VALIDATION_ERROR", "요청값을 확인해 주세요."),
    500: ("COMMON_INTERNAL_ERROR", "서버 처리 중 오류가 발생했습니다."),
}
