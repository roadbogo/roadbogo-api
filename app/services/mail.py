from email.message import EmailMessage
from html import escape
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
    expire_minutes: int | None = None,
) -> None:
    if not is_smtp_configured(config):
        raise MailDeliveryUnavailableError("SMTP is not configured.")

    expire_minutes = expire_minutes or config.auth_password_reset_expire_minutes
    text_body = (
        "안녕하세요, 도로보GO입니다.\n\n"
        "계정 비밀번호 재설정 요청이 접수되었습니다.\n"
        f"아래 링크를 통해 {expire_minutes}분 이내에\n"
        "새로운 비밀번호를 설정해 주세요.\n\n"
        f"{reset_url}\n\n"
        "보안을 위해 이 링크는 한 번만 사용할 수 있으며,\n"
        "유효시간이 지나면 다시 요청해야 합니다.\n\n"
        "본인이 요청하지 않은 경우에는 이 메일을 무시해 주세요.\n"
        "비밀번호는 변경되지 않으며 계정도 그대로 유지됩니다.\n\n"
        "안전한 도로를 위한 연결,\n"
        "도로보GO"
    )
    escaped_url = escape(reset_url)
    escaped_href = escape(reset_url, quote=True)
    html_body = f"""\
<!doctype html>
<html lang="ko">
  <body style="margin:0;padding:0;background:#EEF2F0;font-family:Arial,'Malgun Gothic',sans-serif;color:#5E6F7B;">
    <div style="padding:28px 16px;">
      <div style="max-width:560px;margin:0 auto;">
        <div style="font-size:18px;font-weight:700;color:#26999E;margin:0 0 12px;">도로보GO</div>
        <div style="background:#FCFCFA;border:1px solid #DDE6E2;border-radius:8px;padding:28px;">
          <h1 style="margin:0 0 18px;font-size:24px;line-height:1.35;color:#193345;">비밀번호 재설정 안내</h1>
          <p style="margin:0 0 14px;font-size:15px;line-height:1.7;">안녕하세요, 도로보GO입니다.</p>
          <p style="margin:0 0 20px;font-size:15px;line-height:1.7;">
            계정 비밀번호 재설정 요청이 접수되었습니다.<br>
            아래 버튼을 통해 {expire_minutes}분 이내에 새로운 비밀번호를 설정해 주세요.
          </p>
          <p style="margin:0 0 22px;">
            <a href="{escaped_href}" style="display:inline-block;background:#3C6FE8;color:#FFFFFF;text-decoration:none;font-weight:700;border-radius:6px;padding:12px 18px;font-size:15px;">비밀번호 재설정</a>
          </p>
          <p style="margin:0 0 8px;font-size:13px;line-height:1.6;color:#5E6F7B;">버튼이 열리지 않으면 아래 주소를 브라우저에 입력해 주세요.</p>
          <p style="margin:0 0 22px;font-size:13px;line-height:1.6;word-break:break-all;color:#193345;">{escaped_url}</p>
          <p style="margin:0 0 14px;font-size:14px;line-height:1.7;">
            보안을 위해 이 링크는 한 번만 사용할 수 있으며, 유효시간이 지나면 다시 요청해야 합니다.
          </p>
          <p style="margin:0;font-size:14px;line-height:1.7;">
            본인이 요청하지 않은 경우에는 이 메일을 무시해 주세요. 비밀번호는 변경되지 않으며 계정도 그대로 유지됩니다.
          </p>
        </div>
        <p style="margin:16px 0 0;font-size:13px;line-height:1.6;color:#26999E;">안전한 도로를 위한 연결, 도로보GO</p>
      </div>
    </div>
  </body>
</html>
"""

    message = EmailMessage()
    message["Subject"] = "[도로보GO] 비밀번호 재설정 안내"
    message["From"] = config.smtp_from_email or ""
    message["To"] = to_email
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=10) as smtp:
        if config.smtp_use_tls:
            smtp.starttls()
        if config.smtp_username and config.smtp_password:
            smtp.login(config.smtp_username, config.smtp_password.get_secret_value())
        smtp.send_message(message)
