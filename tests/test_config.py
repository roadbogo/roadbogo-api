import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_supports_single_origin_env_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000"]


def test_cors_origins_supports_comma_separated_env_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://admin.example.com")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == [
        "http://localhost:3000",
        "https://admin.example.com",
    ]


def test_cors_origins_rejects_empty_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " , ")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_origins_rejects_wildcard_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,*")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
