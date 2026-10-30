"""Tests for registration and OTP account activation."""

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import fakeredis
import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import email_verification, otp_store, security
from app.database import Base, get_session, upgrade_sqlite_schema
from app.models import EmailVerificationOTP, User, UserSession
from app.routers import auth as auth_routes


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]]]:
    """Build an isolated API, SQLite database, Redis fake, and SMTP capture."""
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

    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    sent_emails: list[tuple[str, str]] = []
    monkeypatch.setattr(otp_store, "redis_client", fake_redis)
    monkeypatch.setattr(
        security,
        "JWT_SECRET",
        "test-only-jwt-secret-that-is-long-enough-1234567890",
    )
    monkeypatch.setattr(auth_routes, "ensure_email_configured", lambda: None)
    monkeypatch.setattr(
        auth_routes,
        "send_verification_email",
        lambda email, otp: sent_emails.append((email, otp)),
    )

    with TestClient(app) as client:
        yield client, sent_emails, fake_redis, test_session_factory

    fake_redis.flushdb()
    test_engine.dispose()


def test_register_stores_inactive_account_and_verifies_email(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
) -> None:
    client, sent_emails, _, test_session_factory = api_client
    password = "test-password-123"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "player@example.com",
            "password": password,
            "display_name": "Red General",
        },
    )

    assert response.status_code == 201
    account = response.json()
    assert account["is_active"] is False
    assert "password" not in account
    assert "password_hash" not in account
    assert len(sent_emails) == 1

    sent_email, otp = sent_emails[0]
    assert sent_email == "player@example.com"
    assert len(otp) == 6 and otp.isdigit()

    with test_session_factory() as session:
        otp_record = session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == account["id"]
            )
        )
        assert otp_record is not None
        assert otp_record.code_hash != otp
        assert otp_record.attempts == 0

    wrong_otp = "999999" if otp != "999999" else "888888"
    wrong_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "player@example.com", "otp": wrong_otp},
    )
    assert wrong_response.status_code == 400
    with test_session_factory() as session:
        pending_user = session.scalar(
            select(User).where(User.email == "player@example.com")
        )
        otp_record = session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == account["id"]
            )
        )
        assert pending_user is not None and pending_user.is_active is False
        assert otp_record is not None and otp_record.attempts == 1

    verified_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "player@example.com", "otp": otp},
    )
    assert verified_response.status_code == 200
    assert verified_response.json()["is_active"] is True

    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "player@example.com"))
        assert user is not None
        assert user.is_active is True
        assert user.password_hash != password
        assert PasswordHash.recommended().verify(password, user.password_hash)
        assert session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == account["id"]
            )
        ) is None


def test_expired_database_otp_does_not_activate_account(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
) -> None:
    client, sent_emails, _, test_session_factory = api_client
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "expired-player@example.com",
            "password": "test-password-123",
            "display_name": "Expired Player",
        },
    )
    assert registration.status_code == 201
    user_id = registration.json()["id"]
    _, otp = sent_emails[0]

    with test_session_factory() as session:
        otp_record = session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == user_id
            )
        )
        assert otp_record is not None
        otp_record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    verification = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "expired-player@example.com", "otp": otp},
    )
    assert verification.status_code == 400

    with test_session_factory() as session:
        user = session.get(User, user_id)
        assert user is not None and user.is_active is False
        assert session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == user_id
            )
        ) is None


def test_login_supports_email_username_and_rotates_remembered_session(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
) -> None:
    client, sent_emails, _, test_session_factory = api_client
    password = "test-password-123"
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "email": "remember-player@example.com",
            "username": "red_general",
            "password": password,
            "display_name": "Red General",
        },
    )
    assert registration.status_code == 201
    account = registration.json()
    assert account["username"] == "red_general"

    inactive_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": account["email"], "password": password},
    )
    assert inactive_login.status_code == 401

    verification = client.post(
        "/api/v1/auth/verify-email",
        json={"email": account["email"], "otp": sent_emails[0][1]},
    )
    assert verification.status_code == 200

    email_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": account["email"], "password": password},
    )
    assert email_login.status_code == 200
    email_token = email_login.json()
    claims = jwt.decode(
        email_token["access_token"],
        security.JWT_SECRET,
        algorithms=["HS256"],
    )
    assert email_token["expires_in"] == 15 * 60
    assert claims["sub"] == str(account["id"])
    assert claims["exp"] - claims["iat"] == 15 * 60

    bad_password_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": account["email"], "password": "incorrect-password"},
    )
    assert bad_password_login.status_code == 401

    with test_session_factory() as session:
        assert session.scalars(select(UserSession)).all() == []

    remembered_login = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "RED_GENERAL",
            "password": password,
            "remember_me": True,
        },
    )
    assert remembered_login.status_code == 200
    set_cookie = remembered_login.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Max-Age=2592000" in set_cookie
    cookie = SimpleCookie()
    cookie.load(set_cookie)
    old_refresh_token = cookie["refresh_token"].value

    with test_session_factory() as session:
        old_session = session.scalar(select(UserSession))
        assert old_session is not None
        assert old_session.refresh_token_hash == security.hash_token(old_refresh_token)

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={old_refresh_token}"},
    )
    assert refresh_response.status_code == 200
    rotated_cookie = SimpleCookie()
    rotated_cookie.load(refresh_response.headers["set-cookie"])
    new_refresh_token = rotated_cookie["refresh_token"].value
    assert new_refresh_token != old_refresh_token

    with test_session_factory() as session:
        sessions = session.scalars(select(UserSession).order_by(UserSession.id)).all()
        assert len(sessions) == 2
        assert sessions[0].revoked_at is not None
        assert sessions[1].revoked_at is None
        assert sessions[1].refresh_token_hash == security.hash_token(new_refresh_token)

    logout_response = client.post(
        "/api/v1/auth/logout",
        headers={"Cookie": f"refresh_token={new_refresh_token}"},
    )
    assert logout_response.status_code == 204
    cleared_cookie = logout_response.headers["set-cookie"]
    assert "refresh_token=\"\"" in cleared_cookie
    assert "Max-Age=0" in cleared_cookie
    assert "HttpOnly" in cleared_cookie
    assert "Secure" in cleared_cookie

    with test_session_factory() as session:
        sessions = session.scalars(select(UserSession).order_by(UserSession.id)).all()
        assert len(sessions) == 2
        assert sessions[0].revoked_at is not None
        assert sessions[1].revoked_at is not None
        assert sessions[1].refresh_token_hash == security.hash_token(new_refresh_token)

    replay_response = client.post(
        "/api/v1/auth/refresh",
        headers={"Cookie": f"refresh_token={new_refresh_token}"},
    )
    assert replay_response.status_code == 401


def test_startup_migration_adds_username_without_deleting_existing_users() -> None:
    legacy_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        with legacy_engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(254) NOT NULL,
                    display_name VARCHAR(80) NOT NULL,
                    password_hash VARCHAR(512) NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT 0,
                    created_at DATETIME
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO users (email, display_name, password_hash, is_active) "
                "VALUES ('existing@example.com', 'Existing Player', 'hash', 1)"
            )

        upgrade_sqlite_schema(legacy_engine)

        with legacy_engine.connect() as connection:
            columns = {column["name"] for column in inspect(connection).get_columns("users")}
            existing_user = connection.exec_driver_sql(
                "SELECT email, username FROM users WHERE id = 1"
            ).one()
            indexes = inspect(connection).get_indexes("users")

        assert "username" in columns
        assert existing_user == ("existing@example.com", None)
        assert any(index["name"] == "ix_users_username" for index in indexes)
    finally:
        legacy_engine.dispose()


def test_five_wrong_codes_expire_the_otp(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
) -> None:
    client, sent_emails, _, test_session_factory = api_client
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "another-player@example.com",
            "password": "test-password-123",
            "display_name": "Black General",
        },
    )
    assert response.status_code == 201
    account_id = response.json()["id"]
    correct_otp = sent_emails[0][1]
    wrong_otp = "999999" if correct_otp != "999999" else "888888"

    with test_session_factory() as session:
        assert session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == account_id
            )
        ) is not None

    statuses = []
    for _ in range(email_verification.MAX_EMAIL_OTP_ATTEMPTS):
        wrong_response = client.post(
            "/api/v1/auth/verify-email",
            json={"email": "another-player@example.com", "otp": wrong_otp},
        )
        statuses.append(wrong_response.status_code)

    assert statuses == [400] * (email_verification.MAX_EMAIL_OTP_ATTEMPTS - 1) + [429]
    with test_session_factory() as session:
        assert session.scalar(
            select(EmailVerificationOTP).where(
                EmailVerificationOTP.user_id == account_id
            )
        ) is None

    correct_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "another-player@example.com", "otp": correct_otp},
    )
    assert correct_response.status_code == 400


def test_forgot_password_and_one_time_reset_code(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, fake_redis, test_session_factory = api_client
    reset_emails: list[tuple[str, str]] = []
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_email",
        lambda email, otp: reset_emails.append((email, otp)),
    )
    old_password = "old-password-123"
    new_password = "new-password-456"

    with test_session_factory() as session:
        user = User(
            email="reset-player@example.com",
            display_name="Reset Player",
            password_hash=PasswordHash.recommended().hash(old_password),
            is_active=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
        session.add(
            UserSession(
                user_id=user_id,
                refresh_token_hash=security.hash_token("remembered-before-reset"),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        session.commit()

    unknown_response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "unknown-player@example.com"},
    )
    request_response = client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "reset-player@example.com"},
    )

    assert unknown_response.status_code == 202
    assert request_response.status_code == 202
    assert unknown_response.json() == request_response.json()
    assert len(reset_emails) == 1
    sent_email, otp = reset_emails[0]
    assert sent_email == "reset-player@example.com"
    assert len(otp) == 6 and otp.isdigit()

    otp_key = otp_store._password_reset_otp_key(sent_email)
    assert fake_redis.get(otp_key) == otp
    assert 1 <= fake_redis.ttl(otp_key) <= otp_store.OTP_TTL_SECONDS

    mismatch_response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": sent_email,
            "otp": otp,
            "new_password": new_password,
            "confirm_password": "different-password-789",
        },
    )
    assert mismatch_response.status_code == 422

    wrong_otp = "999999" if otp != "999999" else "888888"
    wrong_code_response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": sent_email,
            "otp": wrong_otp,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert wrong_code_response.status_code == 400

    reset_response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": sent_email,
            "otp": otp,
            "new_password": new_password,
            "confirm_password": new_password,
        },
    )
    assert reset_response.status_code == 200
    assert fake_redis.exists(otp_key) == 0

    replay_response = client.post(
        "/api/v1/auth/reset-password",
        json={
            "email": sent_email,
            "otp": otp,
            "new_password": "another-password-789",
            "confirm_password": "another-password-789",
        },
    )
    assert replay_response.status_code == 400

    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == sent_email))
        assert user is not None
        assert user.is_active is True
        assert PasswordHash.recommended().verify(new_password, user.password_hash)
        assert not PasswordHash.recommended().verify(old_password, user.password_hash)
        remembered_session = session.scalar(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        assert remembered_session is not None
        assert remembered_session.revoked_at is not None
