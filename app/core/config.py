from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "roadbogo-api"
    app_env: str = "local"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    internal_api_v1_prefix: str = "/api/internal/v1"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    log_level: str = "INFO"
    db_host: str = ""
    db_port: int = 3306
    db_user: str = "roadbogo"
    db_password: str = ""
    db_scheme: str = Field(
        default="roadbogo",
        validation_alias=AliasChoices("DB_NAME", "DB_SCHEME"),
    )
    minio_endpoint: str = "192.168.0.101:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "roadbogo"
    minio_secure: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        origins = value.split(",") if isinstance(value, str) else value
        normalized = [origin.strip() for origin in origins if origin.strip()]

        if not normalized or "*" in normalized:
            raise ValueError("CORS_ORIGINS must contain explicit origins")

        return normalized


settings = Settings()
