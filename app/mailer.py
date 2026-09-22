"""Minimal email sending: stdlib smtplib, no extra dependency.

If SMTP isn't configured (local dev), the message is printed to the server
console instead of failing, so registration still works without real email.
"""
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

logger = logging.getLogger("app.mailer")


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        print(f"\n[email] SMTP is not configured — printing instead of sending.\n"
              f"  To:      {to}\n  Subject: {subject}\n  {body}\n")
        return

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user or "no-reply@localhost"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password or "")
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                server.starttls()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password or "")
                server.send_message(msg)
    except OSError:
        logger.exception("Failed to send email to %s", to)
        raise


def send_verification_code(to: str, code: str) -> None:
    send_email(
        to,
        f"Код подтверждения — {settings.app_name}",
        f"Ваш код подтверждения: {code}\n\n"
        f"Он действителен 15 минут. Если вы не регистрировались на сайте «{settings.app_name}», "
        f"просто проигнорируйте это письмо.",
    )
