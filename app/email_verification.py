"""Database-backed one-time codes for account email verification."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import EmailVerificationOTP


OTP_TTL_SECONDS = 300
MAX_EMAIL_OTP_ATTEMPTS = 5
PBKDF2_ITERATIONS = 120_000


def _hash_otp(otp: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        otp.encode("ascii"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    ).hex()


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes for timezone-aware columns; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def issue_email_otp(session: Session, user_id: int) -> str:
    """Create a six-digit code and persist its salted hash for five minutes."""
    otp = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(16)
    session.add(
        EmailVerificationOTP(
            user_id=user_id,
            code_hash=_hash_otp(otp, salt),
            salt=salt,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS),
        )
    )
    return otp


def verify_email_otp(session: Session, user_id: int, otp: str) -> int:
    """Check and consume an email code from the database.

    Returns 1 for a valid code, 0 for a wrong code, -1 for an absent or expired
    code, and -2 after the maximum number of incorrect attempts.
    """
    now = datetime.now(timezone.utc)
    record = session.scalar(
        select(EmailVerificationOTP)
        .where(EmailVerificationOTP.user_id == user_id)
        .with_for_update()
    )
    if record is None:
        return -1

    if _as_utc(record.expires_at) <= now:
        session.delete(record)
        session.commit()
        return -1

    if record.attempts >= MAX_EMAIL_OTP_ATTEMPTS:
        session.delete(record)
        session.commit()
        return -2

    matches = hmac.compare_digest(_hash_otp(otp, record.salt), record.code_hash)
    if matches:
        consumed = session.execute(
            delete(EmailVerificationOTP)
            .where(
                EmailVerificationOTP.id == record.id,
                EmailVerificationOTP.expires_at > now,
            )
            .execution_options(synchronize_session=False)
        )
        if consumed.rowcount != 1:
            session.rollback()
            return -1
        return 1

    updated = session.execute(
        update(EmailVerificationOTP)
        .where(
            EmailVerificationOTP.id == record.id,
            EmailVerificationOTP.expires_at > now,
            EmailVerificationOTP.attempts < MAX_EMAIL_OTP_ATTEMPTS,
        )
        .values(attempts=EmailVerificationOTP.attempts + 1)
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        session.rollback()
        return -1

    attempts = session.scalar(
        select(EmailVerificationOTP.attempts).where(
            EmailVerificationOTP.id == record.id
        )
    )
    if attempts is None:
        session.rollback()
        return -1
    if attempts >= MAX_EMAIL_OTP_ATTEMPTS:
        session.execute(
            delete(EmailVerificationOTP).where(EmailVerificationOTP.id == record.id)
        )
        session.commit()
        return -2

    session.commit()
    return 0


def clear_email_otp(session: Session, user_id: int) -> None:
    """Remove any pending email verification code for an account."""
    session.execute(
        delete(EmailVerificationOTP).where(EmailVerificationOTP.user_id == user_id)
    )
