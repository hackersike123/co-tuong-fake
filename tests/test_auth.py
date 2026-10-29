"""Tests for registration and OTP account activation."""

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pwdlib import PasswordHash
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import otp_store
from app.database import Base, get_session
from app.models import User
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
    client, sent_emails, fake_redis, test_session_factory = api_client
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

    otp_key = otp_store._otp_key(account["id"])
    assert fake_redis.get(otp_key) == otp
    assert 1 <= fake_redis.ttl(otp_key) <= otp_store.OTP_TTL_SECONDS

    wrong_otp = "999999" if otp != "999999" else "888888"
    wrong_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "player@example.com", "otp": wrong_otp},
    )
    assert wrong_response.status_code == 400

    verified_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "player@example.com", "otp": otp},
    )
    assert verified_response.status_code == 200
    assert verified_response.json()["is_active"] is True
    assert fake_redis.exists(otp_key) == 0

    with test_session_factory() as session:
        user = session.scalar(select(User).where(User.email == "player@example.com"))
        assert user is not None
        assert user.is_active is True
        assert user.password_hash != password
        assert PasswordHash.recommended().verify(password, user.password_hash)


def test_five_wrong_codes_expire_the_otp(
    api_client: tuple[TestClient, list[tuple[str, str]], fakeredis.FakeRedis, sessionmaker[Session]],
) -> None:
    client, sent_emails, fake_redis, _ = api_client
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
    otp_key = otp_store._otp_key(account_id)
    correct_otp = sent_emails[0][1]
    wrong_otp = "999999" if correct_otp != "999999" else "888888"

    statuses = []
    for _ in range(otp_store.MAX_OTP_ATTEMPTS):
        wrong_response = client.post(
            "/api/v1/auth/verify-email",
            json={"email": "another-player@example.com", "otp": wrong_otp},
        )
        statuses.append(wrong_response.status_code)

    assert statuses == [400] * (otp_store.MAX_OTP_ATTEMPTS - 1) + [429]
    assert fake_redis.exists(otp_key) == 0

    correct_response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "another-player@example.com", "otp": correct_otp},
    )
    assert correct_response.status_code == 400
