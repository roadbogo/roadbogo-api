from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.responses import success_response
from app.dependencies.auth import CurrentUser, get_current_user
from app.schemas.auth import (
    AuthTokenData,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestData,
    RegisterData,
    RegisterRequest,
)
from app.schemas.common import SuccessResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_refresh_cookie(response: Response, result: auth_service.RefreshResult) -> None:
    response.set_cookie(
        key=settings.auth_refresh_cookie_name,
        value=result.raw_refresh_token,
        httponly=True,
        secure=auth_service.refresh_cookie_secure(settings),
        samesite="lax",
        path=auth_service.COOKIE_PATH,
        max_age=auth_service.refresh_cookie_max_age(result.is_persistent, settings),
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.auth_refresh_cookie_name,
        path=auth_service.COOKIE_PATH,
        secure=auth_service.refresh_cookie_secure(settings),
        httponly=True,
        samesite="lax",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=SuccessResponse[RegisterData],
)
def register(
    request: Request,
    payload: RegisterRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    user = auth_service.register_user(db, payload)
    return success_response(
        data={"user": user.model_dump()},
        message="회원가입이 완료되었습니다.",
        trace_id=request.state.trace_id,
    )


@router.post("/login", response_model=SuccessResponse[AuthTokenData])
def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    result = auth_service.login_user(
        db,
        payload,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_refresh_cookie(response, result)
    return success_response(data=result.data.model_dump(), trace_id=request.state.trace_id)


@router.post("/refresh", response_model=SuccessResponse[AuthTokenData])
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = auth_service.refresh_access_token(
            db,
            request.cookies.get(settings.auth_refresh_cookie_name),
        )
    except AppException:
        _delete_refresh_cookie(response)
        raise
    _set_refresh_cookie(response, result)
    return success_response(data=result.data.model_dump(), trace_id=request.state.trace_id)


@router.post("/logout", response_model=SuccessResponse[None])
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    auth_service.logout_user(db, request.cookies.get(settings.auth_refresh_cookie_name))
    _delete_refresh_cookie(response)
    return success_response(
        data=None,
        message="로그아웃되었습니다.",
        trace_id=request.state.trace_id,
    )


@router.get("/me", response_model=SuccessResponse[RegisterData])
def me(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    return success_response(
        data={"user": current_user.summary.model_dump()},
        trace_id=request.state.trace_id,
    )


@router.post(
    "/password-reset/request",
    response_model=SuccessResponse[PasswordResetRequestData],
)
def password_reset_request(
    request: Request,
    payload: PasswordResetRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    data = auth_service.request_password_reset(db, payload)
    return success_response(
        data=data.model_dump(exclude_none=True),
        message="등록된 계정이 있는 경우 비밀번호 재설정 안내가 전송됩니다.",
        trace_id=request.state.trace_id,
    )


@router.post("/password-reset/confirm", response_model=SuccessResponse[None])
def password_reset_confirm(
    request: Request,
    payload: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    auth_service.confirm_password_reset(db, payload)
    return success_response(
        data=None,
        message="비밀번호가 재설정되었습니다.",
        trace_id=request.state.trace_id,
    )
