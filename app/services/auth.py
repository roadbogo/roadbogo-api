from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import re
import secrets
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.exceptions import AppException
from app.core.password_policy import PasswordPolicyError, validate_password_policy
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
from app.models.notification import AuditLog
from app.schemas.auth import (
    AuthTokenData,
    LoginRequest,
    OrganizationSummary,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetRequestData,
    RegisterRequest,
    UpdateMeRequest,
    UserSummary,
    WithdrawMeRequest,
)
from app.services import mail

ACTIVE = "ACTIVE"
GENERAL_USER = "GENERAL_USER"
CLIENT_TYPE_WEB = "WEB"
COOKIE_PATH = "/api/v1/auth"
PHONE_PATTERN = re.compile(r"^\+?[0-9]{8,15}$")


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


def password_policy_error(exc: PasswordPolicyError) -> AppException:
    return auth_error(
        422,
        "USER_PASSWORD_POLICY_VIOLATION",
        "Password does not satisfy the policy.",
        details={"rules": [violation.rule for violation in exc.violations]},
    )


def phone_encryption_unavailable() -> AppException:
    return auth_error(
        503,
        "AUTH_PHONE_ENCRYPTION_UNAVAILABLE",
        "Phone encryption is unavailable.",
    )


def _get_phone_fernet(config: Settings = settings) -> Fernet:
    key = config.auth_phone_encryption_key
    if key is None:
        raise phone_encryption_unavailable()
    try:
        return Fernet(key.get_secret_value().encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise phone_encryption_unavailable() from exc


def normalize_phone(value: str) -> str:
    normalized = re.sub(r"[\s\-().]", "", value.strip())
    if not PHONE_PATTERN.fullmatch(normalized):
        raise auth_error(
            422,
            "AUTH_PHONE_INVALID",
            "Invalid phone number.",
            details={"rules": ["phone_format"]},
        )
    return normalized


def encrypt_phone(value: str, config: Settings = settings) -> bytes:
    return _get_phone_fernet(config).encrypt(value.encode("utf-8"))


def decrypt_phone(value: bytes | None, config: Settings = settings) -> str | None:
    if value is None:
        return None
    try:
        return _get_phone_fernet(config).decrypt(value).decode("utf-8")
    except InvalidToken as exc:
        raise phone_encryption_unavailable() from exc


def ensure_password_policy(password: str) -> None:
    try:
        validate_password_policy(password)
    except PasswordPolicyError as exc:
        raise password_policy_error(exc) from exc


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
        .where(
            UserRole.user_id == user.user_id,
            Role.is_active == 1,
        )
        .order_by(Role.role_code, Permission.permission_code)
    ).all()

    roles = sorted({role_code for role_code, _permission_code in rows})
    permissions = sorted(
        {permission_code for _role_code, permission_code in rows if permission_code}
    )
    organization = None
    if user.organization is not None:
        organization = OrganizationSummary(
            public_id=user.organization.public_id,
            organization_name=user.organization.organization_name,
            organization_type=user.organization.organization_type,
        )
    return UserSummary(
        public_id=user.public_id,
        email=user.email,
        user_name=user.user_name,
        phone=decrypt_phone(user.phone_encrypted),
        account_status=user.account_status,
        organization=organization,
        roles=roles,
        permissions=permissions,
        last_login_at=user.last_login_at,
        updated_at=user.updated_at,
    )


def register_user(db: Session, request: RegisterRequest) -> UserSummary:
    ensure_password_policy(request.password)
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
        db.flush()
        db.refresh(user, attribute_names=["updated_at"])
        user_summary = collect_user_summary(db, user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise auth_error(409, "AUTH_EMAIL_ALREADY_EXISTS", "Email already exists.") from exc
    except Exception:
        db.rollback()
        raise

    return user_summary


def update_current_user_profile(
    db: Session,
    user: User,
    request: UpdateMeRequest,
) -> UserSummary:
    previous_user_name = user.user_name
    previous_phone_encrypted = user.phone_encrypted
    try:
        if "user_name" in request.model_fields_set and request.user_name is not None:
            user.user_name = request.user_name
        if "phone" in request.model_fields_set:
            if request.phone is None:
                user.phone_encrypted = None
            else:
                user.phone_encrypted = encrypt_phone(normalize_phone(request.phone))

        db.flush()
        db.refresh(user, attribute_names=["updated_at"])
        user_summary = collect_user_summary(db, user)
        db.commit()
    except Exception:
        db.rollback()
        user.user_name = previous_user_name
        user.phone_encrypted = previous_phone_encrypted
        raise

    return user_summary


def withdraw_current_user(
    db: Session,
    current_user,
    request: WithdrawMeRequest,
    *,
    trace_id: str,
) -> None:
    user = None
    previous_values = None
    expected_user_id = current_user.user.user_id
    expected_public_id = current_user.user.public_id
    try:
        user = db.scalars(
            select(User)
            .where(
                User.user_id == expected_user_id,
                User.public_id == expected_public_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if (
            user is None
            or user.user_id != expected_user_id
            or user.public_id != expected_public_id
            or user.account_status != ACTIVE
            or user.deleted_at is not None
        ):
            raise account_unavailable()

        active_roles = set(
            db.scalars(
                select(Role.role_code)
                .select_from(UserRole)
                .join(Role, Role.role_id == UserRole.role_id)
                .where(UserRole.user_id == user.user_id, Role.is_active == 1)
            ).all()
        )
        if active_roles != {GENERAL_USER}:
            raise auth_error(
                403,
                "AUTH_WITHDRAWAL_NOT_ALLOWED",
                "운영 계정은 본인 회원탈퇴를 이용할 수 없습니다.",
            )
        if not verify_password_or_dummy(request.current_password, user.password_hash):
            raise auth_error(
                401,
                "AUTH_CURRENT_PASSWORD_INVALID",
                "현재 비밀번호가 일치하지 않습니다.",
            )

        previous_values = {
            "account_status": user.account_status,
            "deactivated_at": user.deactivated_at,
            "deactivated_by_user_id": user.deactivated_by_user_id,
            "deleted_at": user.deleted_at,
            "email": user.email,
            "user_name": user.user_name,
            "phone_encrypted": user.phone_encrypted,
            "password_hash": user.password_hash,
            "password_reset_token_hash": user.password_reset_token_hash,
            "password_reset_token_expires_at": user.password_reset_token_expires_at,
        }
        now = utc_now_naive()
        user.account_status = "INACTIVE"
        user.deactivated_at = now
        user.deactivated_by_user_id = user.user_id
        user.deleted_at = now
        user.email = f"withdrawn+{user.public_id}@roadbogo.invalid"
        user.user_name = "탈퇴한 사용자"
        user.phone_encrypted = None
        user.password_hash = hash_password(secrets.token_urlsafe(32))
        user.password_reset_token_hash = None
        user.password_reset_token_expires_at = None

        db.execute(
            update(UserSession)
            .where(UserSession.user_id == user.user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now, revoke_reason="ACCOUNT_WITHDRAWAL")
        )
        db.add(
            AuditLog(
                public_id=str(uuid4()),
                actor_type="USER",
                actor_user_id=user.user_id,
                action_code="AUTH.ACCOUNT_WITHDRAW",
                resource_type="USER",
                resource_public_id=user.public_id,
                result_status="SUCCESS",
                before_json={"account_status": "ACTIVE", "deleted": False},
                after_json={"account_status": "INACTIVE", "deleted": True},
                trace_id=trace_id,
            )
        )
        db.flush()
        db.commit()
    except Exception:
        db.rollback()
        if user is not None and previous_values is not None:
            for field, value in previous_values.items():
                setattr(user, field, value)
        raise


def issue_auth_tokens(
    db: Session,
    user: User,
    *,
    session: UserSession | None = None,
    remember_me: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
    update_last_login: bool = False,
) -> RefreshResult:
    now = utc_now_naive()
    raw_refresh_token = generate_refresh_token()
    refresh_token_hash = hash_refresh_token(raw_refresh_token)
    expires_at = get_refresh_token_expires_at(now=datetime.now(UTC)).replace(tzinfo=None)
    previous_refresh_token_hash = session.refresh_token_hash if session is not None else None
    previous_expires_at = session.expires_at if session is not None else None
    previous_last_login_at = user.last_login_at

    if session is None:
        session = UserSession(
            public_id=str(uuid4()),
            user_id=user.user_id,
            refresh_token_hash=refresh_token_hash,
            client_type=CLIENT_TYPE_WEB,
            expires_at=expires_at,
            is_persistent=1 if remember_me else 0,
            ip_hash=sha256_or_none(ip_address),
            user_agent_hash=sha256_or_none(user_agent),
        )
        db.add(session)
    else:
        session.refresh_token_hash = refresh_token_hash
        session.expires_at = expires_at
        remember_me = bool(session.is_persistent)

    try:
        if update_last_login:
            user.last_login_at = now
        db.flush()
        if update_last_login:
            db.refresh(user, attribute_names=["updated_at"])
        access_token = create_access_token(user.public_id, session.public_id)
        user_summary = collect_user_summary(db, user)
        db.commit()
    except Exception:
        db.rollback()
        if previous_refresh_token_hash is not None:
            session.refresh_token_hash = previous_refresh_token_hash
            session.expires_at = previous_expires_at
        if update_last_login:
            user.last_login_at = previous_last_login_at
        raise

    expires_in = settings.auth_access_token_expire_minutes * 60
    return RefreshResult(
        raw_refresh_token=raw_refresh_token,
        is_persistent=remember_me,
        data=AuthTokenData(
            access_token=access_token,
            token_type="Bearer",
            expires_in=expires_in,
            user=user_summary,
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
        update_last_login=True,
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
        mail.send_password_reset_email(
            to_email=user.email,
            reset_url=reset_url,
            config=config,
            expire_minutes=config.auth_password_reset_expire_minutes,
        )

    if debug_allowed:
        data.debug_reset_token = raw_token
        data.debug_reset_url = reset_url

    return data


def confirm_password_reset(db: Session, request: PasswordResetConfirmRequest) -> None:
    ensure_password_policy(request.new_password)
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
