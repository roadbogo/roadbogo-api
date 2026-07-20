from collections.abc import Callable

from fastapi import Depends

from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser, get_current_user


def require_permissions(*required: str) -> Callable[..., CurrentUser]:
    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        granted = set(current_user.summary.permissions)
        if not set(required).issubset(granted):
            raise AppException(
                status_code=403,
                code="AUTH_PERMISSION_DENIED",
                message="요청한 기능을 사용할 권한이 없습니다.",
            )
        return current_user

    return dependency
