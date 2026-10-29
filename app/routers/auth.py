"""Account registration routes."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_session
from ..email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
    ensure_email_configured,
    send_password_reset_email,
    send_verification_email,
)
from ..models import User
from ..otp_store import (
    clear_email_otp,
    clear_password_reset_otp,
    consume_password_reset_otp,
    issue_email_otp,
    issue_password_reset_otp,
    verify_email_otp,
)
from ..schemas import (
    ForgotPasswordRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    UserResponse,
    VerifyEmailRequest,
)
from ..security import hash_password


logger = logging.getLogger(__name__)
router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a player account and send an email verification code",
)
def register_account(payload: RegisterRequest, session: SessionDep) -> User:
    """Create an inactive account, store an OTP, and send it by email."""
    email = str(payload.email).strip().lower()

    try:
        ensure_email_configured()
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        ) from exc

    existing_user = session.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        is_active=False,
    )
    session.add(user)

    try:
        session.commit()
    except IntegrityError as exc:
        # The database constraint also protects against simultaneous registrations.
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc

    session.refresh(user)

    try:
        otp = issue_email_otp(user.id)
    except RedisError as exc:
        _delete_pending_user(session, user)
        logger.exception("Could not store email verification code in Redis")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service is temporarily unavailable",
        ) from exc

    try:
        send_verification_email(email, otp)
    except (EmailConfigurationError, EmailDeliveryError) as exc:
        _clear_otp_after_error(user.id)
        _delete_pending_user(session, user)
        logger.exception("Could not send account verification email")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not send verification email",
        ) from exc

    return user


@router.post(
    "/verify-email",
    response_model=UserResponse,
    summary="Verify an email address and activate the account",
)
def verify_account_email(payload: VerifyEmailRequest, session: SessionDep) -> User:
    """Activate an inactive account when its email OTP is valid."""
    email = str(payload.email).strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )
    if user.is_active:
        return user

    try:
        result = verify_email_otp(user.id, payload.otp)
    except RedisError as exc:
        logger.exception("Could not verify email code in Redis")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification service is temporarily unavailable",
        ) from exc

    if result == -2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect verification attempts",
        )
    if result != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code",
        )

    user.is_active = True
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    try:
        clear_email_otp(user.id)
    except RedisError:
        logger.exception("Could not delete a consumed email verification code")

    session.refresh(user)
    return user


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send a password reset code by email",
)
def forgot_password(
    payload: ForgotPasswordRequest,
    session: SessionDep,
) -> MessageResponse:
    """Send a reset code without revealing whether the email has an account."""
    email = str(payload.email).strip().lower()
    generic_message = "If an active account exists for this email, a reset code has been sent."

    try:
        ensure_email_configured()
    except EmailConfigurationError:
        logger.exception("Password reset email service is not configured")
        return MessageResponse(message=generic_message)

    user = session.scalar(
        select(User).where(User.email == email, User.is_active.is_(True))
    )
    if user is None:
        return MessageResponse(message=generic_message)

    try:
        otp = issue_password_reset_otp(user.id)
    except RedisError:
        logger.exception("Could not store password reset code in Redis")
        return MessageResponse(message=generic_message)

    try:
        send_password_reset_email(email, otp)
    except (EmailConfigurationError, EmailDeliveryError):
        _clear_password_reset_otp_after_error(user.id)
        logger.exception("Could not send password reset email")

    return MessageResponse(message=generic_message)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset a password using an emailed code",
)
def reset_password(
    payload: ResetPasswordRequest,
    session: SessionDep,
) -> MessageResponse:
    """Verify the reset code and replace the account's password hash."""
    email = str(payload.email).strip().lower()
    user = session.scalar(
        select(User).where(User.email == email, User.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset code",
        )

    try:
        result = consume_password_reset_otp(user.id, payload.otp)
    except RedisError as exc:
        logger.exception("Could not verify password reset code in Redis")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Password reset service is temporarily unavailable",
        ) from exc

    if result == -2:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many incorrect password reset attempts",
        )
    if result != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset code",
        )

    user.password_hash = hash_password(payload.new_password)
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise

    return MessageResponse(message="Password reset successfully")


def _clear_otp_after_error(user_id: int) -> None:
    try:
        clear_email_otp(user_id)
    except RedisError:
        logger.exception("Could not clear an unsent email verification code")


def _clear_password_reset_otp_after_error(user_id: int) -> None:
    try:
        clear_password_reset_otp(user_id)
    except RedisError:
        logger.exception("Could not clear an unsent password reset code")


def _delete_pending_user(session: Session, user: User) -> None:
    try:
        session.delete(user)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not delete an account after verification setup failed")
