from dataclasses import dataclass

from fastapi.testclient import TestClient

from app.api.v1 import auth as auth_api
from app.core.database import get_db
from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import create_app
from app.schemas.auth import AuthTokenData, UserSummary
from app.services.auth import RefreshResult


@dataclass
class DummyUser:
    public_id: str = "user-public-id"
    email: str = "user@example.com"
    user_name: str = "홍길동"
    account_status: str = "ACTIVE"


@dataclass
class DummySession:
    public_id: str = "session-public-id"


def user_summary() -> UserSummary:
    return UserSummary(
        public_id="user-public-id",
        email="user@example.com",
        user_name="홍길동",
        account_status="ACTIVE",
        roles=["GENERAL_USER"],
        permissions=[],
    )


def token_result(*, persistent: bool) -> RefreshResult:
    return RefreshResult(
        raw_refresh_token="raw-refresh-token",
        is_persistent=persistent,
        data=AuthTokenData(
            access_token="access-token",
            token_type="Bearer",
            expires_in=1800,
            user=user_summary(),
        ),
    )


def client_with_dummy_db() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: object()
    return TestClient(app)


def test_register_response_contract(monkeypatch) -> None:
    monkeypatch.setattr(auth_api.auth_service, "register_user", lambda db, payload: user_summary())
    client = client_with_dummy_db()

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "USER@example.com",
            "user_name": "홍길동",
            "password": "password123",
            "password_confirmation": "password123",
        },
    )

    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"]["user"]["roles"] == ["GENERAL_USER"]
    assert "user_id" not in body["data"]["user"]
    assert body["message"] == "회원가입이 완료되었습니다."


def test_login_sets_httponly_session_or_persistent_cookie(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_api.auth_service,
        "login_user",
        lambda db, payload, ip_address, user_agent: token_result(persistent=False),
    )
    client = client_with_dummy_db()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123", "remember_me": False},
    )

    cookie = response.headers["set-cookie"].lower()
    assert response.json()["data"]["access_token"] == "access-token"
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/api/v1/auth" in cookie
    assert "max-age" not in cookie

    monkeypatch.setattr(
        auth_api.auth_service,
        "login_user",
        lambda db, payload, ip_address, user_agent: token_result(persistent=True),
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "password123", "remember_me": True},
    )
    assert "max-age=" in response.headers["set-cookie"].lower()


def test_refresh_rotates_cookie_and_logout_deletes_cookie(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_api.auth_service,
        "refresh_access_token",
        lambda db, refresh_token: token_result(persistent=True),
    )
    revoked = []
    monkeypatch.setattr(
        auth_api.auth_service,
        "logout_user",
        lambda db, refresh_token: revoked.append(refresh_token),
    )
    client = client_with_dummy_db()
    client.cookies.set("roadbogo_refresh_token", "old-refresh-token", path="/api/v1/auth")

    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert response.json()["data"]["access_token"] == "access-token"
    assert "raw-refresh-token" in response.headers["set-cookie"]

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert revoked == ["raw-refresh-token"]
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_refresh_failure_returns_common_error_and_deletes_cookie(monkeypatch) -> None:
    def raise_invalid_refresh(db, refresh_token):
        raise AppException(
            status_code=401,
            code="AUTH_REFRESH_TOKEN_INVALID",
            message="Invalid refresh token.",
        )

    monkeypatch.setattr(auth_api.auth_service, "refresh_access_token", raise_invalid_refresh)
    client = client_with_dummy_db()
    client.cookies.set("roadbogo_refresh_token", "old-refresh-token", path="/api/v1/auth")

    response = client.post("/api/v1/auth/refresh")
    body = response.json()
    cookie = response.headers["set-cookie"].lower()

    assert response.status_code == 401
    assert body["success"] is False
    assert body["error"]["code"] == "AUTH_REFRESH_TOKEN_INVALID"
    assert body["trace_id"]
    assert "max-age=0" in cookie or "expires=" in cookie
    assert "path=/api/v1/auth" in cookie
    assert "old-refresh-token" not in response.text


def test_me_uses_current_user_dependency() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user=DummyUser(),
        session=DummySession(),
        summary=user_summary(),
    )
    client = TestClient(app)

    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer access-token"})

    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "user@example.com"


def test_password_reset_request_debug_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_api.auth_service,
        "request_password_reset",
        lambda db, payload: auth_api.PasswordResetRequestData(
            accepted=True,
            debug_reset_token="debug-token",
            debug_reset_url="http://localhost:3000/reset-password?token=debug-token",
        ),
    )
    client = client_with_dummy_db()

    response = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["accepted"] is True
    assert response.json()["data"]["debug_reset_token"] == "debug-token"
