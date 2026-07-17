import re
from datetime import UTC, datetime
from typing import Any

from pydantic import Field, field_serializer, field_validator, model_validator

from app.schemas.base import RequestModel


class OrganizationSummary(RequestModel):
    public_id: str
    organization_name: str
    organization_type: str


class UserSummary(RequestModel):
    public_id: str
    email: str
    user_name: str
    phone: str | None = None
    account_status: str
    organization: OrganizationSummary | None = None
    roles: list[str]
    permissions: list[str]
    last_login_at: datetime | None = None
    updated_at: datetime

    @staticmethod
    def serialize_utc_datetime(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        else:
            value = value.astimezone(UTC)
        return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @field_serializer("last_login_at", "updated_at")
    def serialize_datetime(self, value: datetime | None) -> str | None:
        return self.serialize_utc_datetime(value)


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_and_validate_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Invalid email address.")
    return normalized


class RegisterRequest(RequestModel):
    email: str = Field(max_length=254)
    user_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=1, max_length=1024)
    password_confirmation: str = Field(min_length=1, max_length=1024)

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
    new_password: str = Field(min_length=1, max_length=1024)
    new_password_confirmation: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def validate_password_confirmation(self) -> "PasswordResetConfirmRequest":
        if self.new_password != self.new_password_confirmation:
            raise ValueError("Password confirmation does not match.")
        return self


class UpdateMeRequest(RequestModel):
    user_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=32)

    @model_validator(mode="before")
    @classmethod
    def reject_empty_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data:
            raise ValueError("At least one field is required.")
        return data

    @model_validator(mode="after")
    def require_field(self) -> "UpdateMeRequest":
        fields_set = self.model_fields_set
        if "user_name" not in fields_set and "phone" not in fields_set:
            raise ValueError("At least one field is required.")
        if "user_name" in fields_set and self.user_name is None:
            raise ValueError("user_name cannot be null.")
        return self
