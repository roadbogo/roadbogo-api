import re

from pydantic import Field, field_validator, model_validator

from app.schemas.base import RequestModel


class UserSummary(RequestModel):
    public_id: str
    email: str
    user_name: str
    account_status: str
    roles: list[str]
    permissions: list[str]


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_and_validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address.")
    return normalized


class RegisterRequest(RequestModel):
    email: str = Field(max_length=254)
    user_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    password_confirmation: str = Field(min_length=8, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "RegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self


class RegisterData(RequestModel):
    user: UserSummary


class LoginRequest(RequestModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)


class AuthTokenData(RequestModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: UserSummary


class PasswordResetRequest(RequestModel):
    email: str = Field(max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_and_validate_email(value)


class PasswordResetRequestData(RequestModel):
    accepted: bool
    debug_reset_token: str | None = None
    debug_reset_url: str | None = None


class PasswordResetConfirmRequest(RequestModel):
    token: str = Field(min_length=1, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)
    new_password_confirmation: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "PasswordResetConfirmRequest":
        if self.new_password != self.new_password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self
