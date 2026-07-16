import re
from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.schemas.base import RequestModel
from app.core.password_policy import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH


class OrganizationSummary(RequestModel):
    public_id: str
    organization_name: str
    organization_type: str


class UserSummary(RequestModel):
    public_id: str
    email: str
    user_name: str
    account_status: str
    roles: list[str]
    permissions: list[str]
    phone: str | None = None
    organization: OrganizationSummary | None = None
    last_login_at: datetime | None = None


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_and_validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address.")
    return normalized


class RegisterRequest(RequestModel):
    email: str = Field(max_length=254)
    user_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    password_confirmation: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

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


class UpdateMeRequest(RequestModel):
    user_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = re.sub(r"[^0-9+]", "", value)
        if not 8 <= len(normalized.lstrip("+")) <= 15:
            raise ValueError("Invalid phone number.")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UpdateMeRequest":
        if not self.model_fields_set:
            raise ValueError("At least one field is required.")
        return self


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
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    new_password_confirmation: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "PasswordResetConfirmRequest":
        if self.new_password != self.new_password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self
