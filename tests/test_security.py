from datetime import UTC, datetime, timedelta
import re
from uuid import UUID
from pydantic import ValidationError

import jwt
import pytest
from cryptography.fernet import Fernet

from app.core import security
from app.core.config import Settings
from app.core.security import (
    AccessTokenExpiredError,
    InvalidAccessTokenError,
    SecurityConfigurationError,
    _datetime_from_claim,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    get_refresh_token_expires_at,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_password_or_dummy,
    verify_refresh_token_hash,
    encrypt_phone,
    decrypt_phone,
)


AUTH_ENV_KEYS = [
    "AUTH_JWT_SECRET_KEY",
    "AUTH_JWT_ALGORITHM",
    "AUTH_JWT_ISSUER",
    "AUTH_JWT_AUDIENCE",
    "AUTH_ACCESS_TOKEN_EXPIRE_MINUTES",
    "AUTH_REFRESH_TOKEN_EXPIRE_DAYS",
    "AUTH_REFRESH_COOKIE_NAME",
]
SECRET = "s" * 32


def bind_auth_settings(
    monkeypatch: pytest.MonkeyPatch,
    **values: str,
) -> None:
    for key in AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    monkeypatch.setattr(security, "get_settings", lambda: Settings(_env_file=None))


def test_missing_secret_does_not_block_settings_or_app_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch)

    assert Settings(_env_file=None).auth_jwt_secret_key is None

    from app.main import app

    assert app.title


def test_short_secret_fails_only_when_jwt_is_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY="short")

    with pytest.raises(SecurityConfigurationError):
        create_access_token("user-public-id", "session-public-id")


def test_password_hashing_and_verification() -> None:
    password_hash = hash_password("correct-password")

    assert password_hash != "correct-password"
    assert password_hash.startswith("$argon2")
    assert verify_password("correct-password", password_hash) is True
    assert verify_password("wrong-password", password_hash) is False
    assert verify_password("correct-password", "not-a-valid-hash") is False
    assert verify_password_or_dummy("correct-password", None) is False
    assert hash_password("same-password") != hash_password("same-password")


def test_phone_encryption_round_trip_without_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(_env_file=None, AUTH_PHONE_ENCRYPTION_KEY=key),
    )
    encrypted = encrypt_phone("01012345678")
    assert b"01012345678" not in encrypted
    assert decrypt_phone(encrypted) == "01012345678"


def test_phone_decryption_rejects_wrong_key_and_corrupt_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_key = Fernet.generate_key().decode("ascii")
    second_key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(_env_file=None, AUTH_PHONE_ENCRYPTION_KEY=first_key),
    )
    encrypted = encrypt_phone("01012345678")
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: Settings(_env_file=None, AUTH_PHONE_ENCRYPTION_KEY=second_key),
    )
    with pytest.raises(security.SecurityError, match="could not be decrypted"):
        decrypt_phone(encrypted)
    with pytest.raises(security.SecurityError, match="could not be decrypted"):
        decrypt_phone(b"corrupt-ciphertext")


def test_debug_password_reset_response_is_rejected_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            APP_ENV="production",
            AUTH_PASSWORD_RESET_DEBUG_RESPONSE=True,
        )


def test_access_token_create_and_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    now = datetime.now(UTC).replace(microsecond=0)

    token = create_access_token(
        "user-public-id",
        "session-public-id",
        expires_delta=timedelta(minutes=30),
        now=now,
    )
    claims = decode_access_token(token)

    assert claims.sub == "user-public-id"
    assert claims.sid == "session-public-id"
    assert UUID(claims.jti)
    assert claims.token_type == "access"
    assert claims.issued_at == now
    assert claims.expires_at == now + timedelta(minutes=30)


def test_access_token_uses_default_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    now = datetime.now(UTC).replace(microsecond=0)

    claims = decode_access_token(
        create_access_token("user-public-id", "session-public-id", now=now)
    )

    assert claims.expires_at - claims.issued_at == timedelta(minutes=30)


def test_access_token_rejects_naive_now(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)

    with pytest.raises(ValueError):
        create_access_token(
            "user-public-id",
            "session-public-id",
            now=datetime(2026, 1, 1, 0, 0, 0),
        )


def test_access_token_rejects_non_positive_expiration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)

    with pytest.raises(ValueError, match="expiration"):
        create_access_token(
            "user-public-id",
            "session-public-id",
            expires_delta=timedelta(0),
        )

    with pytest.raises(ValueError, match="expiration"):
        create_access_token(
            "user-public-id",
            "session-public-id",
            expires_delta=timedelta(seconds=-1),
        )


def test_access_token_rejects_blank_subject_or_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)

    with pytest.raises(ValueError, match="user_public_id"):
        create_access_token("", "session-public-id")

    with pytest.raises(ValueError, match="user_public_id"):
        create_access_token("   ", "session-public-id")

    with pytest.raises(ValueError, match="session_public_id"):
        create_access_token("user-public-id", "")

    with pytest.raises(ValueError, match="session_public_id"):
        create_access_token("user-public-id", "   ")


def test_access_token_rejects_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    token = create_access_token(
        "user-public-id",
        "session-public-id",
        expires_delta=timedelta(minutes=1),
        now=datetime.now(UTC) - timedelta(minutes=2),
    )

    with pytest.raises(AccessTokenExpiredError):
        decode_access_token(token)


def test_access_token_rejects_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    token = create_access_token("user-public-id", "session-public-id")

    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY="t" * 32)

    with pytest.raises(InvalidAccessTokenError) as exc_info:
        decode_access_token(token)

    assert token not in str(exc_info.value)


def test_access_token_rejects_issuer_and_audience_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    token = create_access_token("user-public-id", "session-public-id")

    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET, AUTH_JWT_ISSUER="other")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)

    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET, AUTH_JWT_AUDIENCE="other")
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_access_token_rejects_missing_claim_wrong_type_and_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bind_auth_settings(monkeypatch, AUTH_JWT_SECRET_KEY=SECRET)
    now = datetime.now(UTC)
    payload = {
        "sub": "user-public-id",
        "jti": str(UUID("00000000-0000-4000-8000-000000000000")),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=30),
        "iss": "roadbogo-api",
        "aud": "roadbogo-web",
    }

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(jwt.encode(payload, SECRET, algorithm="HS256"))

    payload["sid"] = "session-public-id"
    payload["type"] = "refresh"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(jwt.encode(payload, SECRET, algorithm="HS256"))

    payload["type"] = "access"
    payload["sub"] = "   "
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(jwt.encode(payload, SECRET, algorithm="HS256"))

    payload["sub"] = "user-public-id"
    payload["sid"] = "   "
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(jwt.encode(payload, SECRET, algorithm="HS256"))

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token("not-a-jwt")


def test_datetime_from_claim_rejects_bool() -> None:
    with pytest.raises(InvalidAccessTokenError):
        _datetime_from_claim(True)


@pytest.mark.parametrize("exception", [ValueError, OverflowError, OSError])
def test_datetime_from_claim_converts_timestamp_errors(
    monkeypatch: pytest.MonkeyPatch,
    exception: type[Exception],
) -> None:
    class BrokenDatetime:
        @staticmethod
        def fromtimestamp(value: int, tz: UTC) -> datetime:
            raise exception("private timestamp detail")

    monkeypatch.setattr(security, "datetime", BrokenDatetime)

    with pytest.raises(InvalidAccessTokenError) as exc_info:
        _datetime_from_claim(1)

    assert str(exc_info.value) == "Invalid access token."


def test_refresh_token_generation_hashing_and_verification() -> None:
    first_token = generate_refresh_token()
    second_token = generate_refresh_token()
    token_hash = hash_refresh_token(first_token)

    assert first_token != second_token
    assert len(first_token) >= 64
    assert re.fullmatch(r"[0-9a-f]{64}", token_hash)
    assert hash_refresh_token(first_token) == token_hash
    assert verify_refresh_token_hash(first_token, token_hash) is True
    assert verify_refresh_token_hash(second_token, token_hash) is False
    assert verify_refresh_token_hash(first_token, "not-a-valid-hash") is False


def test_refresh_token_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_auth_settings(monkeypatch, AUTH_REFRESH_TOKEN_EXPIRE_DAYS="7")
    now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    expires_at = get_refresh_token_expires_at(now=now)

    assert expires_at == now + timedelta(days=7)
    assert expires_at.tzinfo == UTC

    with pytest.raises(ValueError):
        get_refresh_token_expires_at(now=datetime(2026, 1, 1, 0, 0, 0))
