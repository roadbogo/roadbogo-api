from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "roadbogo-api"
    environment: str = "local"
    backend_cors_origins: list[str] = ["http://localhost:3000"]

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "roadbogo"
    db_password: str = Field(default="", repr=False)

    # 기존 DB_SCHEME 환경변수도 임시 호환
    db_name: str = Field(
        default="roadbogo",
        validation_alias=AliasChoices("DB_NAME", "DB_SCHEME"),
    )

    db_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()