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
    send_verification_email,
)
from ..models import User
from ..otp_store import (
    clear_email_otp,
    issue_email_otp,
    verify_email_otp,
)
from ..schemas import (
    RegisterRequest,
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


def _clear_otp_after_error(user_id: int) -> None:
    try:
        clear_email_otp(user_id)
    except RedisError:
        logger.exception("Could not clear an unsent email verification code")


def _delete_pending_user(session: Session, user: User) -> None:
    try:
        session.delete(user)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not delete an account after verification setup failed")
