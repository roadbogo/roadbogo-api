from dataclasses import dataclass


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 64


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
    if not any(char.isalpha() for char in password):
        violations.append(PasswordPolicyViolation("letter_required"))
    if not any(char.isdigit() for char in password):
        violations.append(PasswordPolicyViolation("number_required"))

    if violations:
        raise PasswordPolicyError(violations)
