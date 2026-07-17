from dataclasses import dataclass
import re


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 64
ASCII_LETTER_PATTERN = re.compile(r"[A-Za-z]")
ASCII_NUMBER_PATTERN = re.compile(r"[0-9]")


@dataclass(frozen=True)
class PasswordPolicyViolation:
    rule: str


class PasswordPolicyError(ValueError):
    def __init__(self, violations: list[PasswordPolicyViolation]) -> None:
        self.violations = violations
        super().__init__("Password does not satisfy the policy.")


def validate_password_policy(password: str) -> None:
    violations: list[PasswordPolicyViolation] = []

    if len(password) < MIN_PASSWORD_LENGTH:
        violations.append(PasswordPolicyViolation("min_length"))
    if len(password) > MAX_PASSWORD_LENGTH:
        violations.append(PasswordPolicyViolation("max_length"))
    if not ASCII_LETTER_PATTERN.search(password):
        violations.append(PasswordPolicyViolation("letter_required"))
    if not ASCII_NUMBER_PATTERN.search(password):
        violations.append(PasswordPolicyViolation("number_required"))

    if violations:
        raise PasswordPolicyError(violations)
