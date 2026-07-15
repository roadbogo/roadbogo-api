from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(
        default="도로보GO API",
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


@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()