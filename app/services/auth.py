from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from uuid import uuid4

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.exceptions import AppException
from app.core.security import (
    create_access_token,
    generate_password_reset_token,
    generate_refresh_token,
    get_refresh_token_expires_at,
    hash_password,
    hash_password_reset_token,
    hash_refresh_token,
    verify_password_or_dummy,
)
from app.models.auth import Permission, Role, RolePermission, User, UserRole, UserSession
from app.schemas.auth import (
    AuthTokenData,
    LoginRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestData,
    RegisterRequest,
    UserSummary,
)
from app.services import mail

ACTIVE = "ACTIVE"
GENERAL_USER = "GENERAL_USER"
CLIENT_TYPE_WEB = "WEB"
COOKIE_PATH = "/api/v1/auth"


@dataclass(frozen=True)
class RefreshResult:
    raw_refresh_token: str
    is_persistent: bool
    data: AuthTokenData


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def sha256_or_none(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def refresh_cookie_secure(config: Settings = settings) -> bool:
    return config.app_env not in {"local", "test"}


def refresh_cookie_max_age(is_persistent: bool, config: Settings = settings) -> int | None:
    if not is_persistent:
        return None
    return config.auth_refresh_token_expire_days * 24 * 60 * 60


def auth_error(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> AppException:
    return AppException(status_code=status_code, code=code, message=message, details=details)


def invalid_credentials() -> AppException:
    return auth_error(401, "AUTH_INVALID_CREDENTIALS", "Invalid email or password.")


def account_unavailable() -> AppException:
    return auth_error(403, "AUTH_ACCOUNT_UNAVAILABLE", "Account is unavailable.")


def _user_by_email_statement(email: str) -> Select[tuple[User]]:
    return select(User).where(User.email == email)


def get_user_by_public_id(db: Session, public_id: str) -> User | None:
    return db.execute(select(User).where(User.public_id == public_id)).scalar_one_or_none()


def get_session_by_public_id(db: Session, public_id: str) -> UserSession | None:
    return db.execute(
        select(UserSession).where(UserSession.public_id == public_id)
    ).scalar_one_or_none()


def get_session_by_refresh_token(
    db: Session,
    refresh_token: str,
    *,
    for_update: bool = False,
) -> UserSession | None:
    statement = select(UserSession).where(
        UserSession.refresh_token_hash == hash_refresh_token(refresh_token)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.execute(statement).scalar_one_or_none()


def collect_user_summary(db: Session, user: User) -> UserSummary:
    rows = db.execute(
        select(Role.role_code, Permission.permission_code)
        .select_from(UserRole)
        .join(Role, Role.role_id == UserRole.role_id)
        .outerjoin(RolePermission, RolePermission.role_id == Role.role_id)
        .outerjoin(Permission, Permission.permission_id == RolePermission.permission_id)
        .where(UserRole.user_id == user.user_id)
        .order_by(Role.role_code, Permission.permission_code)
    ).all()

    roles = sorted({role_code for role_code, _permission_code in rows})
    permissions = sorted(
        {permission_code for _role_code, permission_code in rows if permission_code}
    )
    return UserSummary(
        public_id=user.public_id,
        email=user.email,
        user_name=user.user_name,
        account_status=user.account_status,
        roles=roles,
        permissions=permissions,
    )


def register_user(db: Session, request: RegisterRequest) -> UserSummary:
    existing = db.execute(_user_by_email_statement(request.email)).scalar_one_or_none()
    if existing is not None:
        raise auth_error(409, "AUTH_EMAIL_ALREADY_EXISTS", "Email already exists.")

    role = db.execute(select(Role).where(Role.role_code == GENERAL_USER)).scalar_one_or_none()
    if role is None:
        raise auth_error(
            500,
            "AUTH_GENERAL_USER_ROLE_NOT_CONFIGURED",
            "GENERAL_USER role is not configured.",
        )

    user = User(
        public_id=str(uuid4()),
        email=request.email,
        password_hash=hash_password(request.password),
        user_name=request.user_name,
        account_status=ACTIVE,
        deleted_at=None,
    )
    db.add(user)

    try:
        db.flush()
        db.add(UserRole(user_id=user.user_id, role_id=role.role_id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise auth_error(409, "AUTH_EMAIL_ALREADY_EXISTS", "Email already exists.") from exc

    db.refresh(user)
    return collect_user_summary(db, user)


def issue_auth_tokens(
    db: Session,
    user: User,
    *,
    session: UserSession | None = None,
    remember_me: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> RefreshResult:
    now = utc_now_naive()
    raw_refresh_token = generate_refresh_token()
    expires_at = get_refresh_token_expires_at(now=datetime.now(UTC)).replace(tzinfo=None)
    if session is None:
        session = UserSession(
            public_id=str(uuid4()),
            user_id=user.user_id,
            refresh_token_hash=hash_refresh_token(raw_refresh_token),
            client_type=CLIENT_TYPE_WEB,
            expires_at=expires_at,
            is_persistent=1 if remember_me else 0,
            ip_hash=sha256_or_none(ip_address),
            user_agent_hash=sha256_or_none(user_agent),
        )
        db.add(session)
    else:
        session.refresh_token_hash = hash_refresh_token(raw_refresh_token)
        session.expires_at = expires_at
        remember_me = bool(session.is_persistent)

    user.last_login_at = now
    db.commit()
    db.refresh(session)
    db.refresh(user)
    access_token = create_access_token(user.public_id, session.public_id)
    expires_in = settings.auth_access_token_expire_minutes * 60
    return RefreshResult(
        raw_refresh_token=raw_refresh_token,
        is_persistent=remember_me,
        data=AuthTokenData(
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            user=collect_user_summary(db, user),
        ),
    )


def login_user(
    db: Session,
    request: LoginRequest,
    *,
    ip_address: str | None,
    user_agent: str | None,
) -> RefreshResult:
    user = db.execute(_user_by_email_statement(request.email)).scalar_one_or_none()
    password_hash = user.password_hash if user is not None else None
    if not verify_password_or_dummy(request.password, password_hash):
        raise invalid_credentials()

    if user is None:
        raise invalid_credentials()
    if user.deleted_at is not None or user.account_status != ACTIVE:
        raise account_unavailable()

    return issue_auth_tokens(
        db,
        user,
        remember_me=request.remember_me,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def refresh_access_token(db: Session, refresh_token: str | None) -> RefreshResult:
    if not refresh_token:
        raise auth_error(401, "AUTH_REFRESH_TOKEN_INVALID", "Invalid refresh token.")

    session = get_session_by_refresh_token(db, refresh_token, for_update=True)
    now = utc_now_naive()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise auth_error(401, "AUTH_REFRESH_TOKEN_INVALID", "Invalid refresh token.")

    user = db.get(User, session.user_id)
    if user is None or user.deleted_at is not None or user.account_status != ACTIVE:
        raise auth_error(401, "AUTH_REFRESH_TOKEN_INVALID", "Invalid refresh token.")

    return issue_auth_tokens(db, user, session=session, remember_me=bool(session.is_persistent))


def logout_user(db: Session, refresh_token: str | None) -> None:
    if not refresh_token:
        return

    session = get_session_by_refresh_token(db, refresh_token)
    if session is None or session.revoked_at is not None:
        return

    session.revoked_at = utc_now_naive()
    session.revoke_reason = "LOGOUT"
    db.commit()


def request_password_reset(
    db: Session,
    request: PasswordResetRequest,
    *,
    config: Settings = settings,
) -> PasswordResetRequestData:
    debug_allowed = config.app_env in {"local", "test"} and config.auth_password_reset_debug_response
    if not mail.is_smtp_configured(config) and not debug_allowed:
        raise auth_error(
            503,
            "AUTH_PASSWORD_RESET_DELIVERY_UNAVAILABLE",
            "Password reset delivery is unavailable.",
        )

    data = PasswordResetRequestData(accepted=True)
    user = db.execute(_user_by_email_statement(request.email)).scalar_one_or_none()
    if user is None or user.deleted_at is not None or user.account_status != ACTIVE:
        return data

    raw_token = generate_password_reset_token()
    reset_url = f"{config.frontend_base_url}/reset-password?token={raw_token}"
    user.password_reset_token_hash = hash_password_reset_token(raw_token)
    user.password_reset_token_expires_at = utc_now_naive() + timedelta(
        minutes=config.auth_password_reset_expire_minutes
    )
    db.commit()

    if mail.is_smtp_configured(config):
        mail.send_password_reset_email(to_email=user.email, reset_url=reset_url, config=config)

    if debug_allowed:
        data.debug_reset_token = raw_token
        data.debug_reset_url = reset_url

    return data


def confirm_password_reset(db: Session, request: PasswordResetConfirmRequest) -> None:
    token_hash = hash_password_reset_token(request.token)
    user = db.execute(
        select(User).where(User.password_reset_token_hash == token_hash).with_for_update()
    ).scalar_one_or_none()
    now = utc_now_naive()

    if user is None:
        raise auth_error(
            401,
            "AUTH_PASSWORD_RESET_TOKEN_INVALID",
            "Invalid password reset token.",
        )
    if user.password_reset_token_expires_at is None or user.password_reset_token_expires_at <= now:
        raise auth_error(
            401,
            "AUTH_PASSWORD_RESET_TOKEN_EXPIRED",
            "Password reset token has expired.",
        )
    if user.deleted_at is not None or user.account_status != ACTIVE:
        raise account_unavailable()

    user.password_hash = hash_password(request.new_password)
    user.password_changed_at = now
    user.password_reset_token_hash = None
    user.password_reset_token_expires_at = None
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now, revoke_reason="PASSWORD_RESET")
    )
    db.commit()
