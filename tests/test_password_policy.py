import pytest

from app.core.password_policy import PasswordPolicyError, validate_password_policy


@pytest.mark.parametrize(
    "password",
    [
        "password1",
        "Roadbogo2026",
        "Password1!",
    ],
)
def test_password_policy_accepts_ascii_letter_and_number(password: str) -> None:
    validate_password_policy(password)


@pytest.mark.parametrize(
    ("password", "expected_rules"),
    [
        ("12345678", ["letter_required"]),
        ("password", ["number_required"]),
        ("가나다라마바사1", ["letter_required"]),
        ("password١", ["number_required"]),
        ("Passw1!", ["min_length"]),
        ("P" + "a" * 63 + "1", ["max_length"]),
    ],
)
def test_password_policy_rejects_missing_ascii_requirements(
    password: str,
    expected_rules: list[str],
) -> None:
    with pytest.raises(PasswordPolicyError) as exc_info:
        validate_password_policy(password)

    assert [violation.rule for violation in exc_info.value.violations] == expected_rules
    assert password not in str(exc_info.value)
