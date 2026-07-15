from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "roadbogo-api"
    environment: str = "local"
    backend_cors_origins: list[str] = ["http://localhost:3000"]
    db_host: str = ""
    db_port: int = 3306
    db_user: str = "roadbogo"
    db_password: str
    db_scheme: str = "roadbogo"
    minio_endpoint: str = "192.168.0.101:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "roadbogo"
    minio_secure: bool = False


settings = Settings()
