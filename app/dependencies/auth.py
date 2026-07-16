from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AppException
from app.core.security import (
    AccessTokenExpiredError,
    InvalidAccessTokenError,
    decode_access_token,
)
from app.models.auth import User, UserSession
from app.schemas.auth import UserSummary
from app.services.auth import ACTIVE, collect_user_summary, get_session_by_public_id, get_user_by_public_id


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session: UserSession
    summary: UserSummary


def _access_error(code: str, message: str) -> AppException:
    return AppException(status_code=401, code=code, message=message)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> CurrentUser:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _access_error("AUTH_ACCESS_TOKEN_MISSING", "Access token is required.")

    try:
        claims = decode_access_token(token)
    except AccessTokenExpiredError as exc:
        raise _access_error("AUTH_ACCESS_TOKEN_EXPIRED", "Access token has expired.") from exc
    except InvalidAccessTokenError as exc:
        raise _access_error("AUTH_ACCESS_TOKEN_INVALID", "Invalid access token.") from exc

    user = get_user_by_public_id(db, claims.sub)
    if user is None:
        raise _access_error("AUTH_ACCESS_TOKEN_INVALID", "Invalid access token.")

    session = get_session_by_public_id(db, claims.sid)
    now = datetime.now(UTC).replace(tzinfo=None)
    if (
        session is None
        or session.user_id != user.user_id
        or session.revoked_at is not None
        or session.expires_at <= now
    ):
        raise _access_error("AUTH_SESSION_INVALID", "Invalid session.")

    if user.deleted_at is not None or user.account_status != ACTIVE:
        raise AppException(
            status_code=403,
            code="AUTH_ACCOUNT_UNAVAILABLE",
            message="Account is unavailable.",
        )

    return CurrentUser(user=user, session=session, summary=collect_user_summary(db, user))
