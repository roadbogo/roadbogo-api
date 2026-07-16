from functools import lru_cache
from typing import Annotated, Any

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(
        default="roadbogo-api",
        validation_alias="APP_NAME",
    )
    app_env: str = Field(
        default="local",
        validation_alias="APP_ENV",
    )
    app_version: str = Field(
        default="0.1.0",
        validation_alias="APP_VERSION",
    )
    api_v1_prefix: str = Field(
        default="/api/v1",
        validation_alias="API_V1_PREFIX",
    )
    internal_api_v1_prefix: str = Field(
        default="/api/internal/v1",
        validation_alias="INTERNAL_API_V1_PREFIX",
    )

    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias="CORS_ORIGINS",
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
    )

    db_name: str = Field(
        default="roadbogo",
        validation_alias=AliasChoices("DB_NAME", "DB_SCHEME"),
    )
    db_host: str = Field(
        default="localhost",
        validation_alias="DB_HOST",
    )
    db_port: int = Field(
        default=3306,
        validation_alias="DB_PORT",
    )
    db_user: str = Field(
        default="roadbogo",
        validation_alias="DB_USER",
    )
    db_password: str = Field(
        default="change-me",
        validation_alias="DB_PASSWORD",
    )
    db_scheme: str = Field(
        default="roadbogo",
        validation_alias="DB_SCHEME",
    )
    db_echo: bool = False

    minio_endpoint: str = Field(
        default="192.168.0.101:9000",
        validation_alias="MINIO_ENDPOINT",
    )
    minio_access_key: str = Field(
        default="",
        validation_alias="MINIO_ACCESS_KEY",
    )
    minio_secret_key: str = Field(
        default="",
        validation_alias="MINIO_SECRET_KEY",
    )
    minio_bucket: str = Field(
        default="roadbogo",
        validation_alias="MINIO_BUCKET",
    )
    minio_secure: bool = Field(
        default=False,
        validation_alias="MINIO_SECURE",
    )

    auth_jwt_secret_key: SecretStr | None = Field(
        default=None,
        validation_alias="AUTH_JWT_SECRET_KEY",
    )
    auth_jwt_algorithm: str = Field(
        default="HS256",
        validation_alias="AUTH_JWT_ALGORITHM",
    )
    auth_jwt_issuer: str = Field(
        default="roadbogo-api",
        validation_alias="AUTH_JWT_ISSUER",
    )
    auth_jwt_audience: str = Field(
        default="roadbogo-web",
        validation_alias="AUTH_JWT_AUDIENCE",
    )
    auth_access_token_expire_minutes: int = Field(
        default=30,
        validation_alias="AUTH_ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    auth_refresh_token_expire_days: int = Field(
        default=7,
        validation_alias="AUTH_REFRESH_TOKEN_EXPIRE_DAYS",
    )
    auth_refresh_cookie_name: str = Field(
        default="roadbogo_refresh_token",
        validation_alias="AUTH_REFRESH_COOKIE_NAME",
    )
    auth_phone_encryption_key: SecretStr | None = Field(
        default=None,
        validation_alias="AUTH_PHONE_ENCRYPTION_KEY",
    )
    frontend_base_url: str = Field(
        default="http://localhost:3000",
        validation_alias="FRONTEND_BASE_URL",
    )
    auth_password_reset_expire_minutes: int = Field(
        default=30,
        validation_alias="AUTH_PASSWORD_RESET_EXPIRE_MINUTES",
    )
    auth_password_reset_debug_response: bool = Field(
        default=False,
        validation_alias="AUTH_PASSWORD_RESET_DEBUG_RESPONSE",
    )
    smtp_host: str | None = Field(default=None, validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: str | None = Field(default=None, validation_alias="SMTP_FROM_EMAIL")
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str] | Any:
        if isinstance(value, str):
            origins = [
                origin.strip()
                for origin in value.split(",")
                if origin.strip()
            ]
            cls.validate_cors_origins(origins)
            return origins

        if isinstance(value, list):
            cls.validate_cors_origins(value)
            return value

        return value

    @staticmethod
    def validate_cors_origins(origins: list[str]) -> None:
        if not origins:
            raise ValueError(
                "CORS_ORIGINS must include at least one origin."
            )

        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS cannot include '*' "
                "when credentials are enabled."
            )

    @field_validator("auth_jwt_secret_key")
    @classmethod
    def validate_auth_jwt_secret_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value

        if not value.get_secret_value().strip():
            raise ValueError("AUTH_JWT_SECRET_KEY cannot be blank.")

        return value

    @field_validator("auth_jwt_algorithm")
    @classmethod
    def validate_auth_jwt_algorithm(cls, value: str) -> str:
        if value != "HS256":
            raise ValueError("AUTH_JWT_ALGORITHM must be HS256.")

        return value

    @field_validator("auth_access_token_expire_minutes", "auth_refresh_token_expire_days")
    @classmethod
    def validate_positive_expiration(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Authentication expiration values must be at least 1.")

        return value

    @field_validator("auth_password_reset_expire_minutes", "smtp_port")
    @classmethod
    def validate_positive_auth_account_values(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Authentication account values must be at least 1.")

        return value

    @model_validator(mode="after")
    def validate_password_reset_debug_response(self) -> "Settings":
        if self.auth_password_reset_debug_response and self.app_env not in {"local", "test"}:
            raise ValueError(
                "AUTH_PASSWORD_RESET_DEBUG_RESPONSE is only allowed in local or test."
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
