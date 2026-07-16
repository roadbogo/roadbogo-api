import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
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
