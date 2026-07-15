from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "roadbogo-api"
    environment: str = "local"
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "roadbogo"
    db_password: str
    db_scheme: str = "roadbogo"


settings = Settings()
