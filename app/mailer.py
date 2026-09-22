"""Sends the verification code by whichever transport is configured — see
Settings for the order. Falls back to printing it to the console so local dev
and CI work without any email setup at all.
"""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from .config import settings

logger = logging.getLogger("app.mailer")


def send_email(to: str, subject: str, body: str) -> None:
    if settings.brevo_api_key:
        _send_via_brevo(to, subject, body)
    elif settings.smtp_host:
        _send_via_smtp(to, subject, body)
    else:
        print(f"\n[email] No mail transport configured — printing instead of sending.\n"
              f"  To:      {to}\n  Subject: {subject}\n  {body}\n")


def _from_address() -> str:
    return settings.smtp_from or settings.smtp_user or "no-reply@localhost"


def _send_via_brevo(to: str, subject: str, body: str) -> None:
    """HTTP API (port 443) — works even where outbound SMTP ports are blocked,
    e.g. Render's free plan. https://developers.brevo.com/reference/sendtransacemail"""
    key = (settings.brevo_api_key or "").strip()
    try:
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": key, "content-type": "application/json"},
            json={"sender": {"email": _from_address()}, "to": [{"email": to}],
                  "subject": subject, "textContent": body},
            timeout=10,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # Brevo's response body has the real reason (bad key, unverified sender,
        # unactivated account, ...) — the status code alone doesn't say which.
        logger.error("Brevo rejected the email to %s: %s %s — key starts with %r, len=%d, from=%r",
                     to, exc.response.status_code, exc.response.text, key[:8], len(key), _from_address())
    except httpx.HTTPError:
        logger.exception("Failed to send email to %s via Brevo", to)
        raise


def _send_via_smtp(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = _from_address()
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
        logger.exception("Failed to send email to %s via SMTP", to)
        raise


def send_verification_code(to: str, code: str) -> None:
    send_email(
        to,
        f"Код подтверждения — {settings.app_name}",
        f"Ваш код подтверждения: {code}\n\n"
        f"Он действителен 15 минут. Если вы не регистрировались на сайте «{settings.app_name}», "
        f"просто проигнорируйте это письмо.",
    )
