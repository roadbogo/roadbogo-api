from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.core.security import create_access_token, hash_refresh_token
from app.dependencies.auth import get_current_user
from app.models.auth import User, UserSession


class FakeRequest:
    def __init__(self, authorization: str | None) -> None:
        self.headers = {}
        if authorization is not None:
            self.headers["Authorization"] = authorization


class FakeResult:
    def __init__(self, value, rows=None) -> None:
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.value

    def all(self):
        return self.rows


class FakeDb:
    def __init__(self, user: User | None, session: UserSession | None) -> None:
        self.user = user
        self.session = session

    def execute(self, statement):
        statement_text = str(statement)
        if "FROM users" in statement_text:
            return FakeResult(self.user)
        if "FROM user_roles" in statement_text:
            return FakeResult(None, [("GENERAL_USER", None)])
        return FakeResult(self.session)


def make_user_and_session() -> tuple[User, UserSession]:
    user = User(
        user_id=1,
        public_id="user-public-id",
        email="user@example.com",
        password_hash="$argon2",
        user_name="홍길동",
        account_status="ACTIVE",
        updated_at=datetime(2026, 7, 17, 5, 10, 0),
    )
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=1,
        refresh_token_hash=hash_refresh_token("refresh"),
        client_type="WEB",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        is_persistent=0,
    )
    return user, session


def bind_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_JWT_SECRET_KEY", "s" * 32)
    get_settings.cache_clear()


def test_current_user_rejects_missing_access_token() -> None:
    with pytest.raises(Exception) as exc_info:
        get_current_user(FakeRequest(None), FakeDb(None, None))

    assert exc_info.value.code == "AUTH_ACCESS_TOKEN_MISSING"


def test_current_user_returns_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_secret(monkeypatch)
    user, session = make_user_and_session()
    token = create_access_token(user.public_id, session.public_id)

    current = get_current_user(
        FakeRequest(f"Bearer {token}"),
        FakeDb(user, session),
    )

    assert current.user.public_id == "user-public-id"
    assert current.summary.email == "user@example.com"


def test_current_user_rejects_revoked_session(monkeypatch: pytest.MonkeyPatch) -> None:
    bind_secret(monkeypatch)
    user, session = make_user_and_session()
    session.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    token = create_access_token(user.public_id, session.public_id)

    with pytest.raises(Exception) as exc_info:
        get_current_user(FakeRequest(f"Bearer {token}"), FakeDb(user, session))

    assert exc_info.value.code == "AUTH_SESSION_INVALID"
