from app.core.config import Settings
from app.services import mail


class FakeSmtp:
    sent_messages = []

    def __init__(self, host, port, timeout) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username, password) -> None:
        self.login_args = (username, password)

    def send_message(self, message) -> None:
        self.sent_messages.append(message)


def test_password_reset_email_has_korean_text_and_html(monkeypatch) -> None:
    FakeSmtp.sent_messages = []
    monkeypatch.setattr(mail.smtplib, "SMTP", FakeSmtp)
    config = Settings(
        _env_file=None,
        SMTP_HOST="smtp.example.com",
        SMTP_FROM_EMAIL="noreply@example.com",
        SMTP_USERNAME="smtp-user",
        SMTP_PASSWORD="smtp-secret",
        AUTH_PASSWORD_RESET_EXPIRE_MINUTES=45,
    )
    reset_url = "https://app.example.com/reset-password?token=a&next=<script>"

    mail.send_password_reset_email(
        to_email="user@example.com",
        reset_url=reset_url,
        config=config,
    )

    assert len(FakeSmtp.sent_messages) == 1
    message = FakeSmtp.sent_messages[0]
    assert message["Subject"] == "[도로보GO] 비밀번호 재설정 안내"
    assert message["To"] == "user@example.com"

    text_body = message.get_body(preferencelist=("plain",)).get_content()
    html_body = message.get_body(preferencelist=("html",)).get_content()
    assert "안녕하세요, 도로보GO입니다." in text_body
    assert "45분 이내" in text_body
    assert reset_url in text_body
    assert "비밀번호 재설정" in html_body
    assert "href=\"https://app.example.com/reset-password?token=a&amp;next=&lt;script&gt;\"" in html_body
    assert "https://app.example.com/reset-password?token=a&amp;next=&lt;script&gt;" in html_body
    assert "smtp-secret" not in text_body
    assert "smtp-secret" not in html_body
    assert "AUTH_JWT_SECRET_KEY" not in html_body
    assert "AUTH_PHONE_ENCRYPTION_KEY" not in html_body
