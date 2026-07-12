from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "roadbogo-api"
    environment: str = "local"
    backend_cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
