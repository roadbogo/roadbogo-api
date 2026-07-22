import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    UpdateMeRequest,
    WithdrawMeRequest,
)


def test_register_request_normalizes_email_and_forbids_roles() -> None:
    payload = RegisterRequest(
        email=" USER@Example.COM ",
        user_name="홍길동",
        password="password123",
        password_confirmation="password123",
    )

    assert payload.email == "user@example.com"

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            user_name="홍길동",
            password="password123",
            password_confirmation="password123",
            role="SYSTEM_ADMIN",
        )


def test_password_confirmations_must_match() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="user@example.com",
            user_name="홍길동",
            password="password123",
            password_confirmation="different123",
        )

    with pytest.raises(ValidationError):
        PasswordResetConfirmRequest(
            token="token",
            new_password="newPassword123",
            new_password_confirmation="different123",
        )


def test_login_request_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="not-an-email", password="password123")


def test_update_me_request_requires_allowed_fields() -> None:
    assert UpdateMeRequest(user_name="Hong Gil Dong").user_name == "Hong Gil Dong"
    assert UpdateMeRequest(phone=None).phone is None

    with pytest.raises(ValidationError):
        UpdateMeRequest()

    with pytest.raises(ValidationError):
        UpdateMeRequest(user_name=None)

    with pytest.raises(ValidationError):
        UpdateMeRequest(email="user@example.com")


def test_withdraw_me_request_contract() -> None:
    assert WithdrawMeRequest(current_password="password").current_password == "password"

    for payload in ({}, {"current_password": ""}, {"current_password": "x" * 129}):
        with pytest.raises(ValidationError):
            WithdrawMeRequest(**payload)

    with pytest.raises(ValidationError):
        WithdrawMeRequest(current_password="password", user_id=1)
