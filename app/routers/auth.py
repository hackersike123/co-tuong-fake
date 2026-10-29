"""Account registration routes."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.exceptions import RedisError
from sqlalchemy import func, or_, select, update
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
from ..models import User, UserSession
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
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
    VerifyEmailRequest,
)
from ..security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from ..settings import REFRESH_TOKEN_TTL_SECONDS


logger = logging.getLogger(__name__)
router = APIRouter()
SessionDep = Annotated[Session, Depends(get_session)]
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes for timezone-aware columns; treat them as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _revoke_refresh_token(session: Session, token: str | None) -> None:
    if not token:
        return
    user_session = session.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == hash_token(token))
    )
    if user_session is not None and user_session.revoked_at is None:
        user_session.revoked_at = datetime.now(timezone.utc)
        session.commit()


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email/username or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Sign in with an email address or username",
)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenResponse:
    """Return an access JWT and optionally create a remembered browser session."""
    identifier = payload.identifier.lower()
    user = session.scalar(
        select(User).where(
            or_(
                func.lower(User.email) == identifier,
                func.lower(User.username) == identifier,
            )
        )
    )
    if user is None or not user.is_active or not verify_password(
        payload.password, user.password_hash
    ):
        raise _invalid_credentials()

    try:
        access_token, expires_in = create_access_token(
            user.id, user.email, user.username
        )
    except RuntimeError as exc:
        logger.exception("JWT signing is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from exc

    current_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    _revoke_refresh_token(session, current_refresh_token)

    if payload.remember_me:
        refresh_token = create_refresh_token()
        session.add(
            UserSession(
                user_id=user.id,
                refresh_token_hash=hash_token(refresh_token),
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
            )
        )
        session.commit()
        _set_refresh_cookie(response, refresh_token)
    else:
        _clear_refresh_cookie(response)

    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the remembered session and renew the access token",
)
def refresh_access_token(
    request: Request,
    response: Response,
    session: SessionDep,
) -> TokenResponse:
    """Rotate a valid refresh cookie and return a new short-lived JWT."""
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not refresh_token:
        raise _invalid_credentials()

    now = datetime.now(timezone.utc)
    user_session = session.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_token(refresh_token)
        )
    )
    if (
        user_session is None
        or user_session.revoked_at is not None
        or _as_utc(user_session.expires_at) <= now
    ):
        raise _invalid_credentials()

    user = session.get(User, user_session.user_id)
    if user is None or not user.is_active:
        user_session.revoked_at = now
        session.commit()
        raise _invalid_credentials()

    try:
        access_token, expires_in = create_access_token(
            user.id, user.email, user.username
        )
    except RuntimeError as exc:
        logger.exception("JWT signing is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        ) from exc

    claimed = session.execute(
        update(UserSession)
        .where(
            UserSession.id == user_session.id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .values(revoked_at=now)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        session.rollback()
        raise _invalid_credentials()

    user_session.revoked_at = now
    new_refresh_token = create_refresh_token()
    session.add(
        UserSession(
            user_id=user.id,
            refresh_token_hash=hash_token(new_refresh_token),
            expires_at=now + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
        )
    )
    session.commit()
    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token, expires_in=expires_in)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def logout(
    request: Request,
    response: Response,
    session: SessionDep,
) -> Response:
    """Revoke the presented remembered session and clear its cookie."""
    _revoke_refresh_token(session, request.cookies.get(REFRESH_COOKIE_NAME))
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


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
    if existing_user is None and payload.username is not None:
        existing_user = session.scalar(
            select(User).where(func.lower(User.username) == payload.username)
        )
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email or username is already registered",
        )

    user = User(
        email=email,
        username=payload.username,
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
            detail="Email or username is already registered",
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
        otp = issue_password_reset_otp(email)
    except RedisError:
        logger.exception("Could not store password reset code in Redis")
        return MessageResponse(message=generic_message)

    try:
        send_password_reset_email(email, otp)
    except (EmailConfigurationError, EmailDeliveryError):
        _clear_password_reset_otp_after_error(email)
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
        result = consume_password_reset_otp(email, payload.otp)
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
    session.execute(
        update(UserSession)
        .where(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
        .execution_options(synchronize_session=False)
    )
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


def _clear_password_reset_otp_after_error(email: str) -> None:
    try:
        clear_password_reset_otp(email)
    except RedisError:
        logger.exception("Could not clear an unsent password reset code")


def _delete_pending_user(session: Session, user: User) -> None:
    try:
        session.delete(user)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not delete an account after verification setup failed")
