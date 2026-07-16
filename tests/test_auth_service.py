from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.security import hash_password, hash_password_reset_token
from app.models.auth import User
from app.schemas.auth import PasswordResetConfirmRequest
from app.services import auth as auth_service


class FakeResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeDb:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.committed = False
        self.updated = False

    def execute(self, statement):
        statement_text = str(statement)
        if statement_text.startswith("UPDATE"):
            self.updated = True
        return FakeResult(self.user)

    def commit(self):
        self.committed = True


def test_password_reset_confirm_hashes_password_and_revokes_sessions() -> None:
    user = User(
        user_id=1,
        public_id="user-public-id",
        email="user@example.com",
        password_hash=hash_password("old-password"),
        user_name="홍길동",
        account_status="ACTIVE",
        password_reset_token_hash=hash_password_reset_token("reset-token"),
        password_reset_token_expires_at=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(minutes=30),
    )
    db = FakeDb(user)

    auth_service.confirm_password_reset(
        db,
        PasswordResetConfirmRequest(
            token="reset-token",
            new_password="newPassword123",
            new_password_confirmation="newPassword123",
        ),
    )

    assert user.password_hash.startswith("$argon2")
    assert user.password_reset_token_hash is None
    assert user.password_reset_token_expires_at is None
    assert user.password_changed_at is not None
    assert db.updated is True
    assert db.committed is True


def test_password_reset_delivery_unavailable_is_checked_before_lookup() -> None:
    db = FakeDb()
    config = Settings(_env_file=None, APP_ENV="production")

    try:
        auth_service.request_password_reset(
            db,
            auth_service.PasswordResetRequest(email="missing@example.com"),
            config=config,
        )
    except Exception as exc:
        assert exc.code == "AUTH_PASSWORD_RESET_DELIVERY_UNAVAILABLE"
    else:
        raise AssertionError("Expected delivery unavailable error.")


def test_refresh_cookie_options() -> None:
    config = Settings(_env_file=None, APP_ENV="test", AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7)

    assert auth_service.refresh_cookie_secure(config) is False
    assert auth_service.refresh_cookie_max_age(False, config) is None
    assert auth_service.refresh_cookie_max_age(True, config) == 7 * 24 * 60 * 60
