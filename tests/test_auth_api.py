from dataclasses import dataclass

from fastapi.testclient import TestClient
import pytest

from app.api.v1 import auth as auth_api
from app.core.database import get_db
from app.core.exceptions import AppException
from app.dependencies.auth import CurrentUser, get_current_user
from app.main import create_app
from app.schemas.auth import AuthTokenData, UserSummary
from app.services.auth import RefreshResult


USER_FIELD_SET = {
    "public_id",
    "email",
    "user_name",
    "phone",
    "account_status",
    "organization",
    "roles",
    "permissions",
    "last_login_at",
    "updated_at",
}


@dataclass
class DummyUser:
    public_id: str = "user-public-id"
    email: str = "user@example.com"
    user_name: str = "Hong Gil Dong"
    account_status: str = "ACTIVE"


@dataclass
class DummySession:
    public_id: str = "session-public-id"


def user_summary() -> UserSummary:
    return UserSummary(
        public_id="user-public-id",
        email="user@example.com",
        user_name="Hong Gil Dong",
        phone=None,
        account_status="ACTIVE",
        organization=None,
        roles=["GENERAL_USER"],
        permissions=[],
        last_login_at=None,
        updated_at="2026-07-17T05:10:00.000Z",
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
            "user_name": "Hong Gil Dong",
            "password": "password123",
            "password_confirmation": "password123",
        },
    )
    body = response.json()

    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"].keys() == {"user"}
    assert set(body["data"]["user"]) == USER_FIELD_SET
    assert body["data"]["user"]["email"] == "user@example.com"
    assert body["data"]["user"]["roles"] == ["GENERAL_USER"]
    assert body["data"]["user"]["account_status"] == "ACTIVE"
    assert body["data"]["user"]["organization"] is None
    assert body["data"]["user"]["phone"] is None
    assert body["data"]["user"]["last_login_at"] is None
    assert body["data"]["user"]["updated_at"].endswith("Z")
    assert body["message"] == "회원가입이 완료되었습니다."
    assert "access_token" not in body["data"]
    assert "refresh_token" not in response.text
    assert "set-cookie" not in response.headers
    assert "user_id" not in body["data"]["user"]
    assert "password_hash" not in body["data"]["user"]
    assert "phone_encrypted" not in body["data"]["user"]


def test_public_register_is_in_openapi() -> None:
    client = client_with_dummy_db()

    response = client.get("/openapi.json")

    assert "/api/v1/auth/register" in response.json()["paths"]


def test_withdraw_me_api_success_and_cookie_deletion(monkeypatch) -> None:
    app = create_app()
    current_user = CurrentUser(
        user=DummyUser(),
        session=DummySession(),
        summary=user_summary(),
    )
    calls = []

    def fake_withdraw(db, authenticated_user, payload, *, trace_id):
        calls.append((db, authenticated_user, payload.current_password, trace_id))

    monkeypatch.setattr(auth_api.auth_service, "withdraw_current_user", fake_withdraw)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: current_user
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/me/withdraw",
        json={"current_password": "current-password"},
    )

    assert response.status_code == 200
    assert response.json()["data"] is None
    assert response.json()["message"] == "회원 탈퇴가 완료되었습니다."
    assert calls and calls[0][1] is current_user
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert "current-password" not in response.text
    assert "user_id" not in response.text


def test_withdraw_me_api_auth_validation_and_error_envelopes(monkeypatch) -> None:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: object()
    client = TestClient(app)
    no_auth = client.post(
        "/api/v1/auth/me/withdraw", json={"current_password": "password"}
    )

    current_user = CurrentUser(
        user=DummyUser(), session=DummySession(), summary=user_summary()
    )
    app.dependency_overrides[get_current_user] = lambda: current_user
    invalid = [
        client.post("/api/v1/auth/me/withdraw"),
        client.post("/api/v1/auth/me/withdraw", json={"current_password": ""}),
        client.post("/api/v1/auth/me/withdraw", json={"current_password": "x" * 129}),
        client.post(
            "/api/v1/auth/me/withdraw",
            json={"current_password": "password", "user_id": 1},
        ),
    ]

    def raise_error(db, authenticated_user, payload, *, trace_id):
        raise AppException(401, "AUTH_CURRENT_PASSWORD_INVALID", "현재 비밀번호가 일치하지 않습니다.")

    monkeypatch.setattr(auth_api.auth_service, "withdraw_current_user", raise_error)
    password_error = client.post(
        "/api/v1/auth/me/withdraw", json={"current_password": "wrong"}
    )

    assert no_auth.status_code == 401
    assert {response.status_code for response in invalid} == {422}
    assert password_error.status_code == 401
    assert password_error.json()["error"]["code"] == "AUTH_CURRENT_PASSWORD_INVALID"
    assert "/api/v1/auth/me/withdraw" in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(
    ("code", "message"),
    [
        ("AUTH_WITHDRAWAL_NOT_ALLOWED", "운영 계정은 본인 회원탈퇴를 이용할 수 없습니다."),
        ("AUTH_ACCOUNT_UNAVAILABLE", "Account is unavailable."),
    ],
)
def test_withdraw_me_api_preserves_service_error_envelope(monkeypatch, code, message) -> None:
    app = create_app()
    current_user = CurrentUser(
        user=DummyUser(), session=DummySession(), summary=user_summary()
    )
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: current_user
    secret = "current-password-secret"

    def raise_error(db, authenticated_user, payload, *, trace_id):
        raise AppException(403, code, message)

    monkeypatch.setattr(auth_api.auth_service, "withdraw_current_user", raise_error)
    response = TestClient(app).post(
        "/api/v1/auth/me/withdraw", json={"current_password": secret}
    )
    body = response.json()

    assert response.status_code == 403
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["trace_id"]
    assert secret not in response.text
    assert "user_id" not in response.text


@pytest.mark.parametrize(
    "field",
    [
        "role",
        "roles",
        "organization_id",
        "organization_public_id",
        "account_status",
        "permissions",
        "phone",
    ],
)
def test_register_rejects_forbidden_fields(field: str) -> None:
    client = client_with_dummy_db()
    payload = {
        "email": "user@example.com",
        "user_name": "Hong Gil Dong",
        "password": "password123",
        "password_confirmation": "password123",
        field: "forbidden",
    }

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert "password123" not in response.text


def test_register_rejects_empty_payload() -> None:
    client = client_with_dummy_db()

    response = client.post("/api/v1/auth/register", json={})

    assert response.status_code == 422


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
    assert set(response.json()["data"]["user"]) == USER_FIELD_SET
    assert response.json()["data"]["user"]["updated_at"] == "2026-07-17T05:10:00.000Z"
    assert ".000Z" in response.json()["data"]["user"]["updated_at"]
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
    data = response.json()["data"]
    assert data["access_token"] == "access-token"
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 1800
    assert set(data["user"]) == USER_FIELD_SET
    assert data["user"]["updated_at"].endswith("Z")
    assert ".000Z" in data["user"]["updated_at"]
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
    user = response.json()["data"]["user"]
    assert response.json()["data"].keys() == {"user"}
    assert set(user) == USER_FIELD_SET
    assert user["email"] == "user@example.com"
    assert user["updated_at"].endswith("Z")
    assert ".000Z" in user["updated_at"]


def test_update_me_uses_current_user_dependency(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_api.auth_service,
        "update_current_user_profile",
        lambda db, user, payload: user_summary(),
    )
    app = create_app()
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user=DummyUser(),
        session=DummySession(),
        summary=user_summary(),
    )
    client = TestClient(app)

    response = client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer access-token"},
        json={"user_name": "Hong Gil Dong"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["message"] == "본인 정보가 수정되었습니다."
    assert set(body["data"]["user"]) == USER_FIELD_SET
    assert body["data"]["user"]["public_id"] == "user-public-id"
    assert body["data"]["user"]["updated_at"] == "2026-07-17T05:10:00.000Z"
    assert "user_id" not in body["data"]["user"]


def test_update_me_rejects_unknown_fields() -> None:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user=DummyUser(),
        session=DummySession(),
        summary=user_summary(),
    )
    client = TestClient(app)

    response = client.patch(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer access-token"},
        json={"email": "other@example.com"},
    )

    assert response.status_code == 422


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
