from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="도로보GO API", validation_alias="APP_NAME")
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    api_v1_prefix: str = Field(default="/api/v1", validation_alias="API_V1_PREFIX")
    internal_api_v1_prefix: str = Field(
        default="/api/internal/v1",
        validation_alias="INTERNAL_API_V1_PREFIX",
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias="CORS_ORIGINS",
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str] | Any:
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            if "*" in origins:
                msg = "CORS_ORIGINS cannot include '*' when credentials are enabled."
                raise ValueError(msg)
            return origins
        if isinstance(value, list) and "*" in value:
            msg = "CORS_ORIGINS cannot include '*' when credentials are enabled."
            raise ValueError(msg)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
