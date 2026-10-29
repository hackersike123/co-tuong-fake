"""Send account verification codes through an SMTP provider."""

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from .settings import (
    SMTP_FROM_EMAIL,
    SMTP_FROM_NAME,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_STARTTLS,
    SMTP_TIMEOUT_SECONDS,
    SMTP_USERNAME,
    SMTP_USE_SSL,
)


class EmailConfigurationError(RuntimeError):
    """Raised when required SMTP settings are missing or incompatible."""


class EmailDeliveryError(RuntimeError):
    """Raised when the SMTP server cannot accept a verification message."""


def ensure_email_configured() -> None:
    """Fail before creating an account if SMTP credentials are not configured."""
    if not all((SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL)):
        raise EmailConfigurationError("SMTP credentials and sender email are required")
    if SMTP_USE_SSL and SMTP_STARTTLS:
        raise EmailConfigurationError("Use either SMTP SSL or STARTTLS, not both")


def send_verification_email(recipient: str, otp: str) -> None:
    """Send the six-digit verification code using configured SMTP settings."""
    _send_otp_email(
        recipient=recipient,
        otp=otp,
        subject="Verify your Co Tuong account",
        body=(
            f"Your Co Tuong verification code is: {otp}\n\n"
            "This code expires in 5 minutes. If you did not create this account, "
            "you can ignore this email."
        ),
    )


def send_password_reset_email(recipient: str, otp: str) -> None:
    """Send a short-lived password reset code through the configured SMTP provider."""
    _send_otp_email(
        recipient=recipient,
        otp=otp,
        subject="Reset your Co Tuong password",
        body=(
            f"Your Co Tuong password reset code is: {otp}\n\n"
            "This code expires in 5 minutes. If you did not request a password reset, "
            "you can ignore this email."
        ),
    )


def _send_otp_email(recipient: str, otp: str, subject: str, body: str) -> None:
    """Send an OTP email through the configured SMTP settings."""
    ensure_email_configured()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM_EMAIL))
    message["To"] = recipient
    message.set_content(body)

    try:
        if SMTP_USE_SSL:
            with smtplib.SMTP_SSL(
                SMTP_HOST,
                SMTP_PORT,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            ) as server:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(message)
            return

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORT,
            timeout=SMTP_TIMEOUT_SECONDS,
        ) as server:
            server.ehlo()
            if SMTP_STARTTLS:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP server could not send the verification email") from exc
