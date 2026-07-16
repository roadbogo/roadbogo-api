from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings


MIN_JWT_SECRET_BYTES = 32
REFRESH_TOKEN_ENTROPY_BYTES = 64
_PASSWORD_HASH = PasswordHash.recommended()
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "b+l2ZMKkrcT39oDLULdpOQ$"
    "iOTtL6Tqx1sdGVcQacHFvvhoBbv9rG9tFp+LHgPMxyI"
)


class SecurityError(Exception):
    pass


class SecurityConfigurationError(SecurityError):
    pass


class SecurityTokenError(SecurityError):
    pass


class AccessTokenExpiredError(SecurityTokenError):
    pass


class InvalidAccessTokenError(SecurityTokenError):
    pass


@dataclass(frozen=True)
class AccessTokenClaims:
    sub: str
    sid: str
    jti: str
    token_type: Literal["access"]
    issued_at: datetime
    expires_at: datetime


def _get_jwt_secret() -> str:
    settings = get_settings()
    secret = settings.auth_jwt_secret_key
    if secret is None:
        raise SecurityConfigurationError("JWT secret is not configured.")

    secret_value = secret.get_secret_value()
    if not secret_value.strip():
        raise SecurityConfigurationError("JWT secret is not configured.")

    if len(secret_value.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
        raise SecurityConfigurationError("JWT secret must be at least 32 bytes.")

    return secret_value


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware.")

    return value.astimezone(UTC)


def _datetime_from_claim(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InvalidAccessTokenError("Invalid access token.")

    try:
        return datetime.fromtimestamp(value, UTC)
    except (ValueError, OverflowError, OSError) as exc:
        raise InvalidAccessTokenError("Invalid access token.") from exc


def _string_claim(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidAccessTokenError("Invalid access token.")

    return value


def _require_non_blank(value: str, claim_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{claim_name} must not be blank.")

    return value


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with Argon2."""
    return _PASSWORD_HASH.hash(plain_password)


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """Return whether a plaintext password matches a stored password hash."""
    try:
        return _PASSWORD_HASH.verify(plain_password, password_hash)
    except Exception:
        return False


def verify_password_or_dummy(
    plain_password: str,
    password_hash: str | None,
) -> bool:
    """Verify a password hash, or a stable dummy hash when no user hash exists."""
    if password_hash is None:
        verify_password(plain_password, _DUMMY_PASSWORD_HASH)
        return False

    return verify_password(plain_password, password_hash)


def create_access_token(
    user_public_id: str,
    session_public_id: str,
    *,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> str:
    """Create a signed HS256 access token for a public user and session id."""
    settings = get_settings()
    user_public_id = _require_non_blank(user_public_id, "user_public_id")
    session_public_id = _require_non_blank(session_public_id, "session_public_id")
    issued_at = _ensure_aware_utc(now if now is not None else datetime.now(UTC))
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.auth_access_token_expire_minutes)
    )
    expires_at = issued_at + lifetime

    if expires_at <= issued_at:
        raise ValueError("Access token expiration must be after issue time.")

    payload = {
        "sub": user_public_id,
        "sid": session_public_id,
        "jti": str(uuid4()),
        "type": "access",
        "iat": issued_at,
        "exp": expires_at,
        "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience,
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=settings.auth_jwt_algorithm)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Decode and validate a signed HS256 access token."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=["HS256"],
            issuer=settings.auth_jwt_issuer,
            audience=settings.auth_jwt_audience,
            options={
                "require": ["sub", "sid", "jti", "type", "iat", "exp", "iss", "aud"],
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise AccessTokenExpiredError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidAccessTokenError("Invalid access token.") from exc

    if payload.get("type") != "access":
        raise InvalidAccessTokenError("Invalid access token.")

    sub = _string_claim(payload, "sub")
    sid = _string_claim(payload, "sid")
    jti = _string_claim(payload, "jti")

    try:
        UUID(jti)
    except ValueError as exc:
        raise InvalidAccessTokenError("Invalid access token.") from exc

    return AccessTokenClaims(
        sub=sub,
        sid=sid,
        jti=jti,
        token_type="access",
        issued_at=_datetime_from_claim(payload.get("iat")),
        expires_at=_datetime_from_claim(payload.get("exp")),
    )


def generate_refresh_token() -> str:
    """Generate an opaque refresh token with at least 48 bytes of entropy."""
    return secrets.token_urlsafe(REFRESH_TOKEN_ENTROPY_BYTES)


def hash_refresh_token(refresh_token: str) -> str:
    """Return the SHA-256 hex digest for an opaque refresh token."""
    return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()


def generate_password_reset_token() -> str:
    """Generate an opaque password reset token."""
    return secrets.token_urlsafe(48)


def hash_password_reset_token(token: str) -> str:
    """Return the SHA-256 hex digest for an opaque password reset token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_refresh_token_hash(
    refresh_token: str,
    expected_hash: str,
) -> bool:
    """Compare a refresh token with an expected SHA-256 hex digest."""
    if len(expected_hash) != 64 or not all(char in "0123456789abcdef" for char in expected_hash):
        return False

    actual_hash = hash_refresh_token(refresh_token)
    return hmac.compare_digest(actual_hash, expected_hash)


def get_refresh_token_expires_at(
    *,
    now: datetime | None = None,
) -> datetime:
    """Return the configured refresh token expiration time."""
    settings = get_settings()
    issued_at = _ensure_aware_utc(now if now is not None else datetime.now(UTC))
    return issued_at + timedelta(days=settings.auth_refresh_token_expire_days)
