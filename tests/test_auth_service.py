from datetime import UTC, datetime, timedelta

from cryptography.fernet import Fernet
import pytest
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.security import hash_password, hash_password_reset_token, hash_refresh_token
from app.models.auth import Organization, Role, User, UserRole, UserSession
from app.models.notification import AuditLog, EventOutbox
from app.schemas.auth import (
    LoginRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    UpdateMeRequest,
    WithdrawMeRequest,
)
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


class WithdrawalScalarResult:
    def __init__(self, value):
        self.value = value

    def first(self):
        return self.value

    def all(self):
        return self.value


class WithdrawalDb:
    def __init__(
        self,
        user,
        roles,
        *,
        fail_add=False,
        fail_flush=False,
        fail_commit=False,
        fail_update=False,
        refreshed_public_id=None,
    ):
        self.scalar_values = [user, roles]
        self.fail_add = fail_add
        self.fail_flush = fail_flush
        self.fail_commit = fail_commit
        self.fail_update = fail_update
        self.refreshed_public_id = refreshed_public_id
        self.statements = []
        self.added = []
        self.flush_count = self.commit_count = self.rollback_count = 0

    def scalars(self, statement):
        self.statements.append(statement)
        value = self.scalar_values.pop(0)
        if self.refreshed_public_id is not None and len(self.statements) == 1:
            value.public_id = self.refreshed_public_id
        return WithdrawalScalarResult(value)

    def execute(self, statement):
        self.statements.append(statement)
        if self.fail_update:
            raise RuntimeError("update failed")
        return object()

    def add(self, value):
        if self.fail_add:
            raise RuntimeError("add failed")
        self.added.append(value)

    def flush(self):
        self.flush_count += 1
        if self.fail_flush:
            raise RuntimeError("flush failed")

    def commit(self):
        self.commit_count += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    def rollback(self):
        self.rollback_count += 1


def withdrawal_user(**overrides):
    values = {
        "user_id": 11,
        "public_id": "11111111-1111-1111-1111-111111111111",
        "email": "real@example.com",
        "password_hash": hash_password("current-password"),
        "user_name": "Real Name",
        "account_status": "ACTIVE",
        "deactivated_at": None,
        "deactivated_by_user_id": None,
        "deleted_at": None,
        "phone_encrypted": b"encrypted-phone",
        "password_reset_token_hash": "token-hash",
        "password_reset_token_expires_at": datetime(2026, 8, 1),
    }
    values.update(overrides)
    return User(**values)


def withdrawal_current_user(user):
    return type(
        "AuthenticatedUser",
        (),
        {"user": type("AuthenticatedUserModel", (), {
            "user_id": user.user_id, "public_id": user.public_id
        })()},
    )()


def test_withdraw_current_user_anonymizes_revokes_sessions_and_audits(monkeypatch) -> None:
    user = withdrawal_user()
    original_hash = user.password_hash
    db = WithdrawalDb(user, ["GENERAL_USER"])
    generated = []
    monkeypatch.setattr(auth_service.secrets, "token_urlsafe", lambda size: generated.append(size) or "z" * 43)

    auth_service.withdraw_current_user(
        db,
        withdrawal_current_user(user),
        WithdrawMeRequest(current_password="current-password"),
        trace_id="trace-id",
    )

    lock_statement = db.statements[0]
    role_statement = db.statements[1]
    session_statement = db.statements[2]
    assert lock_statement._for_update_arg is not None
    assert lock_statement.get_execution_options()["populate_existing"] is True
    assert "users.user_id" in str(lock_statement)
    assert "users.public_id" in str(lock_statement)
    assert "roles.is_active" in str(role_statement)
    assert user.account_status == "INACTIVE"
    assert user.deactivated_at == user.deleted_at
    assert user.deactivated_by_user_id == user.user_id
    assert user.email == f"withdrawn+{user.public_id}@roadbogo.invalid"
    assert len(user.email) <= 254
    assert user.user_name == "탈퇴한 사용자" and user.phone_encrypted is None
    assert user.password_hash != original_hash and user.password_hash.startswith("$argon2")
    assert generated == [32]
    assert user.password_reset_token_hash is None
    assert user.password_reset_token_expires_at is None
    assert "ACCOUNT_WITHDRAWAL" in str(session_statement.compile().params.values())
    audit = next(value for value in db.added if isinstance(value, AuditLog))
    assert audit.action_code == "AUTH.ACCOUNT_WITHDRAW"
    assert audit.before_json == {"account_status": "ACTIVE", "deleted": False}
    assert audit.after_json == {"account_status": "INACTIVE", "deleted": True}
    assert "real@example.com" not in repr((audit.before_json, audit.after_json))
    assert not any(isinstance(value, EventOutbox) for value in db.added)
    assert db.commit_count == 1


@pytest.mark.parametrize(
    ("roles", "expected_code"),
    [
        ([], "AUTH_WITHDRAWAL_NOT_ALLOWED"),
        (["CONTROLLER"], "AUTH_WITHDRAWAL_NOT_ALLOWED"),
        (["GENERAL_USER", "CONTROLLER"], "AUTH_WITHDRAWAL_NOT_ALLOWED"),
        (["GENERAL_USER", "RESPONDER"], "AUTH_WITHDRAWAL_NOT_ALLOWED"),
        (["SYSTEM_ADMIN"], "AUTH_WITHDRAWAL_NOT_ALLOWED"),
    ],
)
def test_withdraw_current_user_rejects_non_general_user_roles(roles, expected_code) -> None:
    user = withdrawal_user()
    db = WithdrawalDb(user, roles)

    with pytest.raises(Exception) as error:
        auth_service.withdraw_current_user(
            db,
            withdrawal_current_user(user),
            WithdrawMeRequest(current_password="current-password"),
            trace_id="trace-id",
        )

    assert error.value.code == expected_code
    assert db.rollback_count == 1 and db.commit_count == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"account_status": "INACTIVE"},
        {"deleted_at": datetime(2026, 7, 22)},
        {"public_id": "22222222-2222-2222-2222-222222222222"},
    ],
)
def test_withdraw_current_user_revalidates_locked_identity_and_status(overrides) -> None:
    authenticated = withdrawal_user()
    locked = withdrawal_user(**overrides)
    db = WithdrawalDb(locked, ["GENERAL_USER"])

    with pytest.raises(Exception) as error:
        auth_service.withdraw_current_user(
            db,
            withdrawal_current_user(authenticated),
            WithdrawMeRequest(current_password="current-password"),
            trace_id="trace-id",
        )

    assert error.value.code == "AUTH_ACCOUNT_UNAVAILABLE"


def test_withdraw_current_user_uses_primitive_identity_snapshot() -> None:
    user = withdrawal_user()
    original_public_id = user.public_id
    current_user = type("CurrentUser", (), {"user": user})()
    db = WithdrawalDb(
        user,
        ["GENERAL_USER"],
        refreshed_public_id="33333333-3333-3333-3333-333333333333",
    )

    with pytest.raises(Exception) as error:
        auth_service.withdraw_current_user(
            db,
            current_user,
            WithdrawMeRequest(current_password="current-password"),
            trace_id="trace-id",
        )

    statement = db.statements[0]
    assert current_user.user is user
    assert user.public_id != original_public_id
    assert error.value.code == "AUTH_ACCOUNT_UNAVAILABLE"
    assert statement._for_update_arg is not None
    assert statement.get_execution_options()["populate_existing"] is True
    assert "users.user_id" in str(statement)
    assert "users.public_id" in str(statement)


def test_withdraw_current_user_rejects_wrong_password_without_exposure() -> None:
    user = withdrawal_user()
    db = WithdrawalDb(user, ["GENERAL_USER"])
    secret = "wrong-current-password"

    with pytest.raises(Exception) as error:
        auth_service.withdraw_current_user(
            db,
            withdrawal_current_user(user),
            WithdrawMeRequest(current_password=secret),
            trace_id="trace-id",
        )

    assert error.value.code == "AUTH_CURRENT_PASSWORD_INVALID"
    assert secret not in repr(error.value)
    assert user.account_status == "ACTIVE" and user.email == "real@example.com"


@pytest.mark.parametrize("failure", ["update", "add", "flush", "commit"])
def test_withdraw_current_user_failure_rolls_back_and_restores_user(failure) -> None:
    user = withdrawal_user()
    db = WithdrawalDb(
        user,
        ["GENERAL_USER"],
        fail_update=failure == "update",
        fail_add=failure == "add",
        fail_flush=failure == "flush",
        fail_commit=failure == "commit",
    )

    with pytest.raises(RuntimeError):
        auth_service.withdraw_current_user(
            db,
            withdrawal_current_user(user),
            WithdrawMeRequest(current_password="current-password"),
            trace_id="trace-id",
        )

    assert db.rollback_count == 1
    assert user.account_status == "ACTIVE"
    assert user.email == "real@example.com"
    assert user.user_name == "Real Name"
    assert user.deleted_at is None


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


class QueryResult:
    def __init__(self, value=None, rows=None) -> None:
        self.value = value
        self.rows = rows or []

    def scalar_one_or_none(self):
        return self.value

    def all(self):
        return self.rows


class AuthFakeDb:
    def __init__(
        self,
        *,
        email_user: User | None = None,
        role: Role | None = None,
        session: UserSession | None = None,
        get_user: User | None = None,
        fail_flush: Exception | None = None,
        fail_commit: Exception | None = None,
    ) -> None:
        self.email_user = email_user
        self.role = role
        self.session = session
        self.get_user = get_user or email_user
        self.fail_flush = fail_flush
        self.fail_commit = fail_commit
        self.added = []
        self.order = []
        self.committed = False
        self.rolled_back = False
        self.user_role: UserRole | None = None
        self.user_session: UserSession | None = None

    def execute(self, statement):
        statement_text = str(statement)
        if statement_text.startswith("UPDATE"):
            self.order.append("execute:update")
            return QueryResult()
        if "FROM users" in statement_text and "users.email" in statement_text:
            self.order.append("execute:user_by_email")
            return QueryResult(self.email_user)
        if "FROM roles" in statement_text:
            self.order.append("execute:role")
            return QueryResult(self.role)
        if "FROM user_sessions" in statement_text:
            self.order.append("execute:session")
            return QueryResult(self.session)
        if "FROM user_roles" in statement_text:
            self.order.append("summary")
            return QueryResult(rows=[("GENERAL_USER", None)])
        self.order.append("execute:other")
        return QueryResult()

    def add(self, value) -> None:
        self.added.append(value)
        if isinstance(value, UserRole):
            self.order.append("add:UserRole")
            self.user_role = value
        if isinstance(value, UserSession):
            self.order.append("add:UserSession")
            self.user_session = value

    def flush(self) -> None:
        self.order.append("flush")
        if self.fail_flush is not None:
            raise self.fail_flush
        for value in self.added:
            if isinstance(value, User) and value.user_id is None:
                value.user_id = 100
                value.updated_at = datetime(2026, 7, 17, 5, 10, 0)
            if isinstance(value, UserSession) and value.user_session_id is None:
                value.user_session_id = 200

    def commit(self) -> None:
        self.order.append("commit")
        if self.fail_commit is not None:
            raise self.fail_commit
        self.committed = True

    def rollback(self) -> None:
        self.order.append("rollback")
        self.rolled_back = True

    def refresh(self, value, attribute_names=None) -> None:
        self.order.append(f"refresh:{type(value).__name__}")
        if attribute_names == ["updated_at"]:
            value.updated_at = datetime(2026, 7, 17, 5, 10, 1)

    def get(self, model, value):
        return self.get_user


def active_user(*, deleted: bool = False, status: str = "ACTIVE") -> User:
    return User(
        user_id=1,
        public_id="user-public-id",
        email="user@example.com",
        password_hash=hash_password("password123"),
        user_name="홍길동",
        account_status=status,
        updated_at=datetime(2026, 7, 17, 5, 10, 0),
        deleted_at=auth_service.utc_now_naive() if deleted else None,
    )


def general_role() -> Role:
    return Role(role_id=7, role_code="GENERAL_USER", role_name="General")


def login_request() -> LoginRequest:
    return LoginRequest(email="user@example.com", password="password123", remember_me=True)


def test_register_user_assigns_general_user_and_hashes_password() -> None:
    db = AuthFakeDb(role=general_role())

    summary = auth_service.register_user(
        db,
        RegisterRequest(
            email="new@example.com",
            user_name="홍길동",
            password="password123",
            password_confirmation="password123",
        ),
    )
    user = next(value for value in db.added if isinstance(value, User))

    assert db.user_role is not None
    assert db.user_role.role_id == 7
    assert user.password_hash.startswith("$argon2")
    assert user.password_hash != "password123"
    assert summary.roles == ["GENERAL_USER"]
    assert summary.permissions == []
    assert summary.account_status == "ACTIVE"
    assert summary.organization is None
    assert summary.phone is None
    assert summary.last_login_at is None
    assert summary.updated_at == datetime(2026, 7, 17, 5, 10, 1)
    assert user.organization_id is None
    assert user.phone_encrypted is None
    assert user.last_login_at is None
    assert user.deleted_at is None
    assert not hasattr(summary, "user_id")


def test_register_user_uses_common_password_policy() -> None:
    db = AuthFakeDb(role=general_role())

    with pytest.raises(Exception) as exc_info:
        auth_service.register_user(
            db,
            RegisterRequest(
                email="new@example.com",
                user_name="Hong Gil Dong",
                password="password",
                password_confirmation="password",
            ),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "USER_PASSWORD_POLICY_VIOLATION"
    assert exc_info.value.details == {"rules": ["number_required"]}


def test_register_user_duplicate_email_raises_409() -> None:
    db = AuthFakeDb(email_user=active_user(), role=general_role())

    with pytest.raises(Exception) as exc_info:
        auth_service.register_user(
            db,
            RegisterRequest(
                email="user@example.com",
                user_name="홍길동",
                password="password123",
                password_confirmation="password123",
            ),
        )

    assert exc_info.value.code == "AUTH_EMAIL_ALREADY_EXISTS"
    assert exc_info.value.status_code == 409


def test_register_user_missing_general_user_role_raises_safe_error() -> None:
    db = AuthFakeDb(role=None)

    with pytest.raises(Exception) as exc_info:
        auth_service.register_user(
            db,
            RegisterRequest(
                email="new@example.com",
                user_name="Hong Gil Dong",
                password="password123",
                password_confirmation="password123",
            ),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.code == "AUTH_GENERAL_USER_ROLE_NOT_CONFIGURED"
    assert "role_id" not in exc_info.value.message


def test_register_user_rolls_back_on_integrity_error() -> None:
    db = AuthFakeDb(role=general_role(), fail_flush=IntegrityError("stmt", "params", Exception()))

    with pytest.raises(Exception) as exc_info:
        auth_service.register_user(
            db,
            RegisterRequest(
                email="new@example.com",
                user_name="Hong Gil Dong",
                password="password123",
                password_confirmation="password123",
            ),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "AUTH_EMAIL_ALREADY_EXISTS"
    assert db.rolled_back is True


def test_login_missing_user_uses_dummy_and_same_invalid_error(monkeypatch) -> None:
    calls = []

    def fake_verify(password, password_hash):
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr(auth_service, "verify_password_or_dummy", fake_verify)

    with pytest.raises(Exception) as exc_info:
        auth_service.login_user(
            AuthFakeDb(email_user=None),
            login_request(),
            ip_address=None,
            user_agent=None,
        )

    assert calls == [("password123", None)]
    assert exc_info.value.code == "AUTH_INVALID_CREDENTIALS"


def test_login_bad_password_uses_same_invalid_error(monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "verify_password_or_dummy", lambda password, hash_: False)

    with pytest.raises(Exception) as exc_info:
        auth_service.login_user(
            AuthFakeDb(email_user=active_user()),
            login_request(),
            ip_address=None,
            user_agent=None,
        )

    assert exc_info.value.code == "AUTH_INVALID_CREDENTIALS"


@pytest.mark.parametrize(
    ("user", "expected_code"),
    [
        (active_user(status="INACTIVE"), "AUTH_ACCOUNT_UNAVAILABLE"),
        (active_user(deleted=True), "AUTH_ACCOUNT_UNAVAILABLE"),
    ],
)
def test_login_unavailable_account_is_rejected(monkeypatch, user, expected_code) -> None:
    monkeypatch.setattr(auth_service, "verify_password_or_dummy", lambda password, hash_: True)

    with pytest.raises(Exception) as exc_info:
        auth_service.login_user(
            AuthFakeDb(email_user=user),
            login_request(),
            ip_address=None,
            user_agent=None,
        )

    assert exc_info.value.code == expected_code


def test_login_creates_session_with_hashed_refresh_token(monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "verify_password_or_dummy", lambda password, hash_: True)
    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: "raw-refresh-token")
    monkeypatch.setattr(auth_service, "create_access_token", lambda user_id, session_id: "access")
    db = AuthFakeDb(email_user=active_user())

    result = auth_service.login_user(
        db,
        login_request(),
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert result.raw_refresh_token == "raw-refresh-token"
    assert db.user_session is not None
    assert db.user_session.refresh_token_hash == hash_refresh_token("raw-refresh-token")
    assert db.user_session.refresh_token_hash != "raw-refresh-token"
    assert db.user_session.is_persistent == 1
    assert db.committed is True


def test_login_updates_last_login_and_user_updated_at_before_summary(monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "verify_password_or_dummy", lambda password, hash_: True)
    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: "raw-refresh-token")
    monkeypatch.setattr(auth_service, "create_access_token", lambda user_id, session_id: "access")
    user = active_user()
    previous_last_login_at = user.last_login_at
    previous_updated_at = user.updated_at
    db = AuthFakeDb(email_user=user)

    result = auth_service.login_user(
        db,
        login_request(),
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert user.last_login_at is not None
    assert user.last_login_at != previous_last_login_at
    assert result.data.user.updated_at != previous_updated_at
    assert db.order[-1] == "commit"
    assert "refresh:User" in db.order


def test_refresh_rotates_hash_and_preserves_persistence(monkeypatch) -> None:
    user = active_user()
    user.last_login_at = datetime(2026, 7, 17, 1, 30, 20, 123000)
    original_last_login_at = user.last_login_at
    original_updated_at = user.updated_at
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=user.user_id,
        refresh_token_hash=hash_refresh_token("old-refresh-token"),
        client_type="WEB",
        expires_at=auth_service.utc_now_naive() + timedelta(days=1),
        is_persistent=1,
    )
    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: "new-refresh-token")
    monkeypatch.setattr(auth_service, "create_access_token", lambda user_id, session_id: "access")
    db = AuthFakeDb(session=session, get_user=user)

    result = auth_service.refresh_access_token(db, "old-refresh-token")

    assert result.raw_refresh_token == "new-refresh-token"
    assert session.refresh_token_hash == hash_refresh_token("new-refresh-token")
    assert session.is_persistent == 1
    assert user.last_login_at == original_last_login_at
    assert user.updated_at == original_updated_at
    assert result.data.user.last_login_at == original_last_login_at
    assert result.data.user.updated_at == original_updated_at
    assert "refresh:User" not in db.order
    assert db.committed is True


@pytest.mark.parametrize(
    "session",
    [
        UserSession(
            user_session_id=10,
            public_id="session-public-id",
            user_id=1,
            refresh_token_hash=hash_refresh_token("refresh-token"),
            client_type="WEB",
            expires_at=auth_service.utc_now_naive() + timedelta(days=1),
            revoked_at=auth_service.utc_now_naive(),
        ),
        UserSession(
            user_session_id=10,
            public_id="session-public-id",
            user_id=1,
            refresh_token_hash=hash_refresh_token("refresh-token"),
            client_type="WEB",
            expires_at=auth_service.utc_now_naive() - timedelta(seconds=1),
        ),
    ],
)
def test_refresh_rejects_revoked_or_expired_session(session) -> None:
    with pytest.raises(Exception) as exc_info:
        auth_service.refresh_access_token(AuthFakeDb(session=session), "refresh-token")

    assert exc_info.value.code == "AUTH_REFRESH_TOKEN_INVALID"


def test_refresh_rejects_inactive_user() -> None:
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=1,
        refresh_token_hash=hash_refresh_token("refresh-token"),
        client_type="WEB",
        expires_at=auth_service.utc_now_naive() + timedelta(days=1),
    )

    with pytest.raises(Exception) as exc_info:
        auth_service.refresh_access_token(
            AuthFakeDb(session=session, get_user=active_user(status="INACTIVE")),
            "refresh-token",
        )

    assert exc_info.value.code == "AUTH_REFRESH_TOKEN_INVALID"


def test_logout_revokes_session_and_missing_cookie_is_success() -> None:
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=1,
        refresh_token_hash=hash_refresh_token("refresh-token"),
        client_type="WEB",
        expires_at=auth_service.utc_now_naive() + timedelta(days=1),
    )
    db = AuthFakeDb(session=session)

    auth_service.logout_user(db, "refresh-token")
    auth_service.logout_user(db, None)

    assert session.revoked_at is not None
    assert session.revoke_reason == "LOGOUT"
    assert db.committed is True


def test_issue_auth_tokens_rolls_back_when_access_token_creation_fails(monkeypatch) -> None:
    user = active_user()
    db = AuthFakeDb()

    def raise_token_error(user_public_id, session_public_id):
        raise RuntimeError("token failed")

    monkeypatch.setattr(auth_service, "create_access_token", raise_token_error)

    with pytest.raises(RuntimeError):
        auth_service.issue_auth_tokens(db, user, remember_me=False)

    assert db.committed is False
    assert db.rolled_back is True


def test_issue_auth_tokens_restores_existing_session_when_rotation_fails(monkeypatch) -> None:
    user = active_user()
    old_expires_at = auth_service.utc_now_naive() + timedelta(days=1)
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=user.user_id,
        refresh_token_hash=hash_refresh_token("old-refresh-token"),
        client_type="WEB",
        expires_at=old_expires_at,
        is_persistent=1,
    )

    def raise_token_error(user_public_id, session_public_id):
        raise RuntimeError("token failed")

    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: "new-refresh-token")
    monkeypatch.setattr(auth_service, "create_access_token", raise_token_error)
    db = AuthFakeDb()

    with pytest.raises(RuntimeError):
        auth_service.issue_auth_tokens(db, user, session=session)

    assert db.committed is False
    assert db.rolled_back is True
    assert session.refresh_token_hash == hash_refresh_token("old-refresh-token")
    assert session.expires_at == old_expires_at


def test_issue_auth_tokens_order_is_flush_token_then_commit(monkeypatch) -> None:
    user = active_user()
    db = AuthFakeDb()

    def create_token(user_public_id, session_public_id):
        db.order.append("token")
        return "access"

    monkeypatch.setattr(auth_service, "create_access_token", create_token)

    auth_service.issue_auth_tokens(db, user)

    assert db.order[:4] == ["add:UserSession", "flush", "token", "summary"]
    assert db.order[-1] == "commit"


def test_issue_auth_tokens_has_no_db_operation_after_commit(monkeypatch) -> None:
    user = active_user()
    db = AuthFakeDb()

    def create_token(user_public_id, session_public_id):
        db.order.append("token")
        return "access"

    monkeypatch.setattr(auth_service, "create_access_token", create_token)

    auth_service.issue_auth_tokens(db, user)

    assert db.order[-1] == "commit"
    assert not any(item.startswith("refresh:") for item in db.order)
    assert db.order.count("flush") == 1
    assert db.order.count("summary") == 1


def test_issue_auth_tokens_commit_failure_rolls_back(monkeypatch) -> None:
    user = active_user()
    old_expires_at = auth_service.utc_now_naive() + timedelta(days=1)
    session = UserSession(
        user_session_id=10,
        public_id="session-public-id",
        user_id=user.user_id,
        refresh_token_hash=hash_refresh_token("old-refresh-token"),
        client_type="WEB",
        expires_at=old_expires_at,
        is_persistent=1,
    )
    db = AuthFakeDb(fail_commit=RuntimeError("commit failed"))
    monkeypatch.setattr(auth_service, "generate_refresh_token", lambda: "new-refresh-token")
    monkeypatch.setattr(auth_service, "create_access_token", lambda user_id, session_id: "access")

    with pytest.raises(RuntimeError):
        auth_service.issue_auth_tokens(db, user, session=session)

    assert db.committed is False
    assert db.rolled_back is True
    assert db.order[-2:] == ["commit", "rollback"]
    assert session.refresh_token_hash == hash_refresh_token("old-refresh-token")
    assert session.expires_at == old_expires_at


def test_register_user_builds_summary_before_commit() -> None:
    db = AuthFakeDb(role=general_role())

    auth_service.register_user(
        db,
        RegisterRequest(
            email="new@example.com",
            user_name="홍길동",
            password="password123",
            password_confirmation="password123",
        ),
    )

    interesting_order = [
        item
        for item in db.order
        if item in {"flush", "add:UserRole", "refresh:User", "summary", "commit"}
    ]
    assert interesting_order == [
        "flush",
        "add:UserRole",
        "flush",
        "refresh:User",
        "summary",
        "commit",
    ]
    assert db.order[-1] == "commit"


def test_register_user_rolls_back_when_summary_creation_fails(monkeypatch) -> None:
    db = AuthFakeDb(role=general_role())

    def raise_summary_error(db, user):
        raise RuntimeError("summary failed")

    monkeypatch.setattr(auth_service, "collect_user_summary", raise_summary_error)

    with pytest.raises(RuntimeError):
        auth_service.register_user(
            db,
            RegisterRequest(
                email="new@example.com",
                user_name="홍길동",
                password="password123",
                password_confirmation="password123",
            ),
        )

    assert db.committed is False
    assert db.rolled_back is True
    assert db.order[-1] == "rollback"


def test_register_user_does_not_refresh_after_commit() -> None:
    db = AuthFakeDb(role=general_role())

    auth_service.register_user(
        db,
        RegisterRequest(
            email="new@example.com",
            user_name="홍길동",
            password="password123",
            password_confirmation="password123",
        ),
    )

    assert db.order[-1] == "commit"
    assert db.order.index("refresh:User") < db.order.index("commit")


def test_register_user_rolls_back_when_commit_fails() -> None:
    db = AuthFakeDb(role=general_role(), fail_commit=RuntimeError("commit failed"))

    with pytest.raises(RuntimeError):
        auth_service.register_user(
            db,
            RegisterRequest(
                email="new@example.com",
                user_name="Hong Gil Dong",
                password="password123",
                password_confirmation="password123",
            ),
        )

    assert db.committed is False
    assert db.rolled_back is True
    assert db.order[-2:] == ["commit", "rollback"]


def test_collect_user_summary_deduplicates_and_serializes_profile(monkeypatch) -> None:
    key = Fernet.generate_key().decode("utf-8")
    config = Settings(_env_file=None, AUTH_PHONE_ENCRYPTION_KEY=key)
    user = active_user()
    user.phone_encrypted = auth_service.encrypt_phone("+821012345678", config)
    user.last_login_at = datetime(2026, 7, 17, 1, 30, 20, 123000)
    user.organization = Organization(
        organization_id=3,
        public_id="organization-public-id",
        organization_code="CENTER",
        organization_name="Control Center",
        organization_type="CONTROL_CENTER",
    )
    db = AuthFakeDb()
    db.execute = lambda statement: QueryResult(
        rows=[
            ("USER", "INCIDENT.READ"),
            ("USER", "INCIDENT.READ"),
            ("ADMIN", "USER.WRITE"),
        ]
    )
    original_decrypt = auth_service.decrypt_phone
    monkeypatch.setattr(auth_service, "decrypt_phone", lambda value: original_decrypt(value, config))

    summary = auth_service.collect_user_summary(db, user)

    assert summary.phone == "+821012345678"
    assert summary.roles == ["ADMIN", "USER"]
    assert summary.permissions == ["INCIDENT.READ", "USER.WRITE"]
    assert summary.organization is not None
    assert summary.organization.public_id == "organization-public-id"
    assert summary.model_dump()["last_login_at"] == "2026-07-17T01:30:20.123Z"
    assert summary.model_dump()["updated_at"] == "2026-07-17T05:10:00.000Z"
    dumped = summary.model_dump()
    assert "user_id" not in dumped
    assert "phone_encrypted" not in dumped
    assert "organization_id" not in dumped


def test_collect_user_summary_uses_only_active_roles() -> None:
    user = active_user()
    statements = []

    class ActiveRoleDb:
        def execute(self, statement):
            statements.append(statement)
            return QueryResult(rows=[
                ("CONTROLLER", "INCIDENT.READ_ALL"),
                ("CONTROL_MANAGER", "INCIDENT.CLOSE"),
                ("CONTROL_MANAGER", "INCIDENT.CLOSE"),
            ])

    summary = auth_service.collect_user_summary(ActiveRoleDb(), user)

    sql = str(statements[0])
    assert "roles.is_active =" in sql
    assert summary.roles == ["CONTROLLER", "CONTROL_MANAGER"]
    assert summary.permissions == ["INCIDENT.CLOSE", "INCIDENT.READ_ALL"]


def test_collect_user_summary_allows_missing_phone_key_when_phone_is_empty() -> None:
    user = active_user()
    user.phone_encrypted = None

    summary = auth_service.collect_user_summary(AuthFakeDb(), user)

    assert summary.phone is None


def test_decrypt_existing_phone_failure_is_safe() -> None:
    user = active_user()
    user.phone_encrypted = b"not-fernet"

    with pytest.raises(Exception) as exc_info:
        auth_service.collect_user_summary(AuthFakeDb(), user)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_PHONE_ENCRYPTION_UNAVAILABLE"
    assert "not-fernet" not in exc_info.value.message


def test_update_current_user_profile_encrypts_phone_and_commits_before_return(
    monkeypatch,
) -> None:
    key = Fernet.generate_key().decode("utf-8")
    config = Settings(_env_file=None, AUTH_PHONE_ENCRYPTION_KEY=key)
    user = active_user()
    user.last_login_at = datetime(2026, 7, 17, 1, 30, 20, 123000)
    original_last_login_at = user.last_login_at
    original_updated_at = user.updated_at
    db = AuthFakeDb()
    original_encrypt = auth_service.encrypt_phone
    original_decrypt = auth_service.decrypt_phone
    monkeypatch.setattr(auth_service, "encrypt_phone", lambda value: original_encrypt(value, config))
    monkeypatch.setattr(auth_service, "decrypt_phone", lambda value: original_decrypt(value, config))

    summary = auth_service.update_current_user_profile(
        db,
        user,
        UpdateMeRequest(user_name="Updated User", phone="010-1234-5678"),
    )

    assert user.user_name == "Updated User"
    assert user.phone_encrypted is not None
    assert b"01012345678" not in user.phone_encrypted
    assert summary.user_name == "Updated User"
    assert summary.last_login_at == original_last_login_at
    assert summary.updated_at != original_updated_at
    assert db.order[-1] == "commit"
    assert db.order.count("flush") == 1
    assert db.order[-4:] == ["flush", "refresh:User", "summary", "commit"]


def test_update_current_user_profile_allows_phone_delete_without_key() -> None:
    user = active_user()
    user.phone_encrypted = b"old"
    original_updated_at = user.updated_at
    db = AuthFakeDb()

    summary = auth_service.update_current_user_profile(
        db,
        user,
        UpdateMeRequest(phone=None),
    )

    assert user.phone_encrypted is None
    assert summary.phone is None
    assert summary.updated_at != original_updated_at


def test_update_current_user_profile_requires_key_for_phone_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_service.settings, "auth_phone_encryption_key", None)
    user = active_user()

    with pytest.raises(Exception) as exc_info:
        auth_service.update_current_user_profile(
            AuthFakeDb(),
            user,
            UpdateMeRequest(phone="010-1234-5678"),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_PHONE_ENCRYPTION_UNAVAILABLE"


def test_update_current_user_profile_rejects_invalid_phone_and_rolls_back() -> None:
    user = active_user()
    db = AuthFakeDb()

    with pytest.raises(Exception) as exc_info:
        auth_service.update_current_user_profile(
            db,
            user,
            UpdateMeRequest(phone="12"),
        )

    assert exc_info.value.status_code == 422
    assert db.rolled_back is True


def test_password_reset_confirm_uses_common_password_policy() -> None:
    user = User(
        user_id=1,
        public_id="user-public-id",
        email="user@example.com",
        password_hash=hash_password("old-password"),
        user_name="Hong Gil Dong",
        account_status="ACTIVE",
        password_reset_token_hash=hash_password_reset_token("reset-token"),
        password_reset_token_expires_at=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(minutes=30),
    )
    db = FakeDb(user)

    with pytest.raises(Exception) as exc_info:
        auth_service.confirm_password_reset(
            db,
            PasswordResetConfirmRequest(
                token="reset-token",
                new_password="12345678",
                new_password_confirmation="12345678",
            ),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "USER_PASSWORD_POLICY_VIOLATION"
    assert exc_info.value.details == {"rules": ["letter_required"]}
