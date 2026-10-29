"""Integration test for the account OTP flow against configured Redis."""

from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import otp_store
from app.database import Base, get_session
from app.routers import auth as auth_routes


def test_registration_and_activation_with_real_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise register and verify endpoints while using the configured Redis."""
    try:
        otp_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    monkeypatch.setattr(
        otp_store,
        "_otp_key",
        lambda user_id: f"test:email-otp:{namespace}:{user_id}",
    )
    monkeypatch.setattr(
        otp_store,
        "_attempts_key",
        lambda user_id: f"test:email-otp-attempts:{namespace}:{user_id}",
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

    sent_codes: list[tuple[str, str]] = []
    monkeypatch.setattr(auth_routes, "ensure_email_configured", lambda: None)
    monkeypatch.setattr(
        auth_routes,
        "send_verification_email",
        lambda email, otp: sent_codes.append((email, otp)),
    )

    account_id: int | None = None
    try:
        with TestClient(app) as client:
            registration = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"{namespace}@example.com",
                    "password": "integration-test-password",
                    "display_name": "Redis Test Player",
                },
            )
            assert registration.status_code == 201
            account = registration.json()
            account_id = account["id"]
            assert account["is_active"] is False
            assert len(sent_codes) == 1

            email, otp = sent_codes[0]
            assert email == f"{namespace}@example.com"
            assert len(otp) == 6 and otp.isdigit()
            assert otp_store.redis_client.get(otp_store._otp_key(account_id)) == otp
            ttl = otp_store.redis_client.ttl(otp_store._otp_key(account_id))
            assert 1 <= ttl <= otp_store.OTP_TTL_SECONDS

            wrong_otp = "999999" if otp != "999999" else "888888"
            wrong_response = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "otp": wrong_otp},
            )
            assert wrong_response.status_code == 400

            verification = client.post(
                "/api/v1/auth/verify-email",
                json={"email": email, "otp": otp},
            )
            assert verification.status_code == 200
            assert verification.json()["is_active"] is True
            assert otp_store.redis_client.exists(otp_store._otp_key(account_id)) == 0
    finally:
        if account_id is not None:
            try:
                otp_store.clear_email_otp(account_id)
            except RedisError:
                pass
        test_engine.dispose()
