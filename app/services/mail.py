from email.message import EmailMessage
import smtplib

from app.core.config import Settings, settings


class MailDeliveryUnavailableError(Exception):
    pass


def is_smtp_configured(config: Settings = settings) -> bool:
    return bool(config.smtp_host and config.smtp_from_email)


def send_password_reset_email(
    *,
    to_email: str,
    reset_url: str,
    config: Settings = settings,
) -> None:
    if not is_smtp_configured(config):
        raise MailDeliveryUnavailableError("SMTP is not configured.")

    message = EmailMessage()
    message["Subject"] = "Roadbogo password reset"
    message["From"] = config.smtp_from_email or ""
    message["To"] = to_email
    message.set_content(
        "Use the link below to reset your password.\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, ignore this email."
    )

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_username and config.smtp_password:
            smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
        smtp.send_message(message)
