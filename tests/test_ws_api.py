"""End-to-end checks for account, lobby, and PvE commands over WebSocket RPC."""

from collections.abc import Iterator
from typing import Any

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database, email_verification, otp_store, room_store, security
from app.database import Base
from app.routers import auth as auth_routes
from app.routers import rooms as room_routes
from app.routers.ws_api import router as ws_api_router
from app.xiangqi import XiangqiState, apply_move, legal_moves


@pytest.fixture
def websocket_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list[tuple[str, str]], list[tuple[str, str]]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", test_sessions)

    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(room_store, "redis_client", fake_redis)
    monkeypatch.setattr(otp_store, "redis_client", fake_redis)
    monkeypatch.setattr(
        security,
        "JWT_SECRET",
        "websocket-test-secret-that-is-at-least-32-characters",
    )

    verification_emails: list[tuple[str, str]] = []
    reset_emails: list[tuple[str, str]] = []
    monkeypatch.setattr(auth_routes, "ensure_email_configured", lambda: None)
    monkeypatch.setattr(
        auth_routes,
        "send_verification_email",
        lambda email, otp: verification_emails.append((email, otp)),
    )
    monkeypatch.setattr(
        auth_routes,
        "send_password_reset_email",
        lambda email, otp: reset_emails.append((email, otp)),
    )

    async def no_op(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(room_routes.room_hub, "broadcast_lobby", no_op)
    monkeypatch.setattr(room_routes.room_hub, "broadcast_room", no_op)
    monkeypatch.setattr(room_routes.room_hub, "ensure_timer", no_op)

    app = FastAPI()
    app.include_router(ws_api_router, prefix="/api/v1")
    with TestClient(app) as client:
        yield client, verification_emails, reset_emails

    fake_redis.flushdb()
    engine.dispose()


def _request(websocket: Any, request_id: str, event: str, data: dict[str, Any]) -> dict[str, Any]:
    websocket.send_json({"id": request_id, "event": event, "data": data})
    response = websocket.receive_json()
    assert response["id"] == request_id
    assert response["event"] == f"{event}.result"
    return response


def test_websocket_auth_register_verify_login_and_reset_password(
    websocket_client: tuple[TestClient, list[tuple[str, str]], list[tuple[str, str]]],
) -> None:
    client, verification_emails, reset_emails = websocket_client
    with client.websocket_connect("/api/v1/ws") as websocket:
        registered = _request(
            websocket,
            "register-1",
            "auth.register",
            {
                "email": "socket-player@example.com",
                "display_name": "Socket Player",
                "password": "original-password",
            },
        )
        assert registered["ok"] is True
        assert registered["data"]["is_active"] is False
        assert len(verification_emails) == 1
        email, verification_code = verification_emails[0]
        assert email == "socket-player@example.com"
        assert len(verification_code) == 6 and verification_code.isdigit()

        verified = _request(
            websocket,
            "verify-1",
            "auth.verify_email",
            {"email": email, "otp": verification_code},
        )
        assert verified["ok"] is True
        assert verified["data"]["is_active"] is True

        login = _request(
            websocket,
            "login-1",
            "auth.login",
            {"identifier": email, "password": "original-password"},
        )
        assert login["ok"] is True
        assert login["data"]["token_type"] == "bearer"
        assert login["data"]["access_token"]

        _request(
            websocket,
            "forgot-1",
            "auth.forgot_password",
            {"email": email},
        )
        assert len(reset_emails) == 1
        _, reset_code = reset_emails[0]
        changed = _request(
            websocket,
            "reset-1",
            "auth.reset_password",
            {
                "email": email,
                "otp": reset_code,
                "new_password": "changed-password",
                "confirm_password": "changed-password",
            },
        )
        assert changed["ok"] is True

        old_login = _request(
            websocket,
            "login-2",
            "auth.login",
            {"identifier": email, "password": "original-password"},
        )
        assert old_login["ok"] is False
        assert old_login["error"]["status"] == 401
        new_login = _request(
            websocket,
            "login-3",
            "auth.login",
            {"identifier": email, "password": "changed-password"},
        )
        assert new_login["ok"] is True


def test_websocket_room_create_join_ready_start_and_authoritative_state(
    websocket_client: tuple[TestClient, list[tuple[str, str]], list[tuple[str, str]]],
) -> None:
    client, _, _ = websocket_client
    with client.websocket_connect("/api/v1/ws") as websocket:
        created = _request(
            websocket,
            "create-1",
            "room.create",
            {"room_name": "Socket room", "host_name": "Host", "time_per_move": 30},
        )
        assert created["ok"] is True
        host = created["data"]
        assert host["room_name"] == "Socket room"
        assert host["role"] == "player1"

        listed = _request(websocket, "list-1", "room.list", {})
        assert listed["ok"] is True
        assert [room["id"] for room in listed["data"]] == [host["id"]]

        joined = _request(
            websocket,
            "join-1",
            "room.join_code",
            {"room_code": str(host["id"])},
        )
        assert joined["ok"] is True
        player_two = joined["data"]
        assert player_two["role"] == "player2"

        ready = _request(
            websocket,
            "ready-1",
            "room.ready",
            {"room_id": host["id"], "participant_token": player_two["participant_token"]},
        )
        assert ready["ok"] is True
        assert ready["data"]["player2_ready"] is True

        started = _request(
            websocket,
            "start-1",
            "room.start",
            {"room_id": host["id"], "participant_token": host["participant_token"]},
        )
        assert started["ok"] is True
        assert started["data"]["status"] == "playing"

        game = _request(
            websocket,
            "game-1",
            "room.game",
            {"room_id": host["id"], "participant_token": host["participant_token"]},
        )
        assert game["ok"] is True
        assert game["data"]["side_to_move"] == "w"
        assert game["data"]["version"] == 0


def test_websocket_pve_options_start_and_ai_move():
    app = FastAPI()
    app.include_router(ws_api_router, prefix="/api/v1")
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws") as websocket:
        options = _request(websocket, "options-1", "pve.options", {})
        assert options["ok"] is True
        assert options["data"]["difficulties"]["easy"]["default_depth"] == 1

        started = _request(
            websocket,
            "pve-start-1",
            "pve.start",
            {"player_side": "w", "difficulty": "easy"},
        )
        assert started["ok"] is True

        state = XiangqiState.initial()
        player_move = legal_moves(state)[0]
        rejected = _request(
            websocket,
            "player-move-invalid",
            "pve.player_move",
            {
                "fen": state.to_fen(),
                "player_side": "w",
                "from": [9, 0],
                "to": [9, 1],
            },
        )
        assert rejected["ok"] is False
        assert rejected["error"]["status"] == 422

        accepted = _request(
            websocket,
            "player-move-1",
            "pve.player_move",
            {
                "fen": state.to_fen(),
                "player_side": "w",
                "from": list(player_move.origin),
                "to": list(player_move.destination),
            },
        )
        assert accepted["ok"] is True
        after_player_move = apply_move(state, player_move)
        assert accepted["data"]["fen"] == after_player_move.to_fen()
        reply = _request(
            websocket,
            "ai-move-1",
            "pve.ai_move",
            {
                "fen": after_player_move.to_fen(),
                "player_side": "w",
                "difficulty": "easy",
            },
        )
        assert reply["ok"] is True
        assert reply["data"]["ai_side"] == "b"
        assert reply["data"]["fen"] != after_player_move.to_fen()


def test_websocket_rpc_returns_validation_errors_without_echoing_passwords():
    app = FastAPI()
    app.include_router(ws_api_router, prefix="/api/v1")
    client = TestClient(app)
    with client.websocket_connect("/api/v1/ws") as websocket:
        response = _request(
            websocket,
            "invalid-1",
            "auth.register",
            {"email": "not-an-email", "display_name": "Bad", "password": "secret"},
        )
        assert response["ok"] is False
        assert response["error"]["status"] == 422
        assert "secret" not in str(response["error"])

