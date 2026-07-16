import re

from app.core.exceptions import AppException

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


def password_policy_violations(password: str) -> list[str]:
    violations: list[str] = []
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        violations.append("length")
    if not re.search(r"[A-Za-z]", password):
        violations.append("letter")
    if not re.search(r"\d", password):
        violations.append("number")
    return violations


def enforce_password_policy(password: str) -> None:
    violations = password_policy_violations(password)
    if violations:
        raise AppException(
            status_code=422,
            code="USER_PASSWORD_POLICY_VIOLATION",
            message="Password does not meet the password policy.",
            details={"rules": violations},
        )
