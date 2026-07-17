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


def test_auth_jwt_secret_key_is_optional() -> None:
    settings = Settings(_env_file=None)

    assert settings.auth_jwt_secret_key is None


def test_auth_jwt_secret_key_repr_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "x" * 32
    monkeypatch.setenv("AUTH_JWT_SECRET_KEY", secret)

    settings = Settings(_env_file=None)

    assert secret not in repr(settings.auth_jwt_secret_key)
    assert settings.auth_jwt_secret_key is not None
    assert settings.auth_jwt_secret_key.get_secret_value() == secret


def test_phone_encryption_key_repr_does_not_expose_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "x" * 44
    monkeypatch.setenv("AUTH_PHONE_ENCRYPTION_KEY", secret)

    settings = Settings(_env_file=None)

    assert secret not in repr(settings.auth_phone_encryption_key)
    assert settings.auth_phone_encryption_key is not None
    assert settings.auth_phone_encryption_key.get_secret_value() == secret


def test_auth_settings_accept_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET_KEY", "y" * 32)
    monkeypatch.setenv("AUTH_JWT_ISSUER", "issuer")
    monkeypatch.setenv("AUTH_JWT_AUDIENCE", "audience")
    monkeypatch.setenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "14")
    monkeypatch.setenv("AUTH_REFRESH_COOKIE_NAME", "refresh")

    settings = Settings(_env_file=None)

    assert settings.auth_jwt_issuer == "issuer"
    assert settings.auth_jwt_audience == "audience"
    assert settings.auth_access_token_expire_minutes == 45
    assert settings.auth_refresh_token_expire_days == 14
    assert settings.auth_refresh_cookie_name == "refresh"


def test_auth_jwt_secret_key_rejects_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET_KEY", "   ")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_auth_expiration_values_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.delenv("AUTH_ACCESS_TOKEN_EXPIRE_MINUTES")
    monkeypatch.setenv("AUTH_REFRESH_TOKEN_EXPIRE_DAYS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_auth_jwt_algorithm_only_allows_hs256(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTH_JWT_ALGORITHM", "RS256")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
