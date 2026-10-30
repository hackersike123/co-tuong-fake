"""Integration test for database email verification and Redis password resets."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from redis.exceptions import RedisError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import otp_store
from app.database import Base, get_session
from app.models import EmailVerificationOTP, User
from app.routers import auth as auth_routes


def test_email_activation_uses_database_and_password_reset_uses_real_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the registration OTP persists in SQL and reset OTP persists in Redis."""
    try:
        otp_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    redis_prefix = f"test:password-reset:{namespace}:"
    monkeypatch.setattr(
        otp_store,
        "_password_reset_otp_key",
        lambda email: f"{redis_prefix}{email}:code",
    )
    monkeypatch.setattr(
        otp_store,
        "_password_reset_attempts_key",
        lambda email: f"{redis_prefix}{email}:attempts",
    )

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    test_session_factory = sessionmaker(
        bind=test_engine,
        autoflush=False,
        expire_on_commit=False,
    )

    def get_test_session() -> Iterator[Session]:
        with test_session_factory() as session:
            yield session

    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/v1/auth")
    app.dependency_overrides[get_session] = get_test_session

    sent_verification_codes: list[tuple[str, str]] = []
    sent_reset_codes: list[tuple[str, str]] = []
    monkeypatch.setattr(auth_routes, "ensure_email_configured", lambda: None)
    monkeypatch.setattr(
        auth_routes,
        "send_verification_email",
        lambda email, otp: sent_verification_codes.append((email, otp)),
    )
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_email",
        lambda email, otp: sent_reset_codes.append((email, otp)),
    )

    email = f"{namespace}@example.com"
    old_password = "integration-test-password"
    new_password = "integration-reset-password"
    try:
        with TestClient(app) as client:
            registration = client.post(
                "/api/v1/auth/register",
                json={
                    "email": email,
                    "password": old_password,
                    "display_name": "OTP Integration Player",
                },
            )
            assert registration.status_code == 201
            user_id = registration.json()["id"]
            assert registration.json()["is_active"] is False
            verification_email, verification_otp = sent_verification_codes[0]
            assert verification_email == email

            with test_session_factory() as session:
                stored_otp = session.scalar(
                    select(EmailVerificationOTP).where(
                        EmailVerificationOTP.user_id == user_id
                    )
                )
                assert stored_otp is not None
                assert stored_otp.code_hash != verification_otp

            verification = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "otp": verification_otp},
            )
            assert verification.status_code == 200
            assert verification.json()["is_active"] is True
            with test_session_factory() as session:
                assert session.scalar(
                    select(EmailVerificationOTP).where(
                        EmailVerificationOTP.user_id == user_id
                    )
                ) is None

            reset_request = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": email},
            )
            assert reset_request.status_code == 202
            reset_email, reset_otp = sent_reset_codes[0]
            assert reset_email == email
            redis_key = otp_store._password_reset_otp_key(email)
            assert otp_store.redis_client.get(redis_key) == reset_otp
            ttl = otp_store.redis_client.ttl(redis_key)
            assert 1 <= ttl <= otp_store.OTP_TTL_SECONDS

            wrong_reset = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "email": email,
                    "otp": "000000" if reset_otp != "000000" else "000001",
                    "new_password": new_password,
                    "confirm_password": new_password,
                },
            )
            assert wrong_reset.status_code == 400

            reset_response = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "email": email,
                    "otp": reset_otp,
                    "new_password": new_password,
                    "confirm_password": new_password,
                },
            )
            assert reset_response.status_code == 200
            assert otp_store.redis_client.exists(redis_key) == 0

            replay = client.post(
                "/api/v1/auth/reset-password",
                json={
                    "email": email,
                    "otp": reset_otp,
                    "new_password": "another-integration-password",
                    "confirm_password": "another-integration-password",
                },
            )
            assert replay.status_code == 400

        with test_session_factory() as session:
            user = session.scalar(select(User).where(User.id == user_id))
            assert user is not None and user.is_active
            assert PasswordHash.recommended().verify(new_password, user.password_hash)
            assert not PasswordHash.recommended().verify(old_password, user.password_hash)
    finally:
        for key in otp_store.redis_client.scan_iter(match=f"{redis_prefix}*"):
            otp_store.redis_client.delete(key)
        test_engine.dispose()
