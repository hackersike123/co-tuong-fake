"""Tests for Redis-backed public room lifecycle and participant roles."""

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import email_service, room_store
from app.email_service import EmailConfigurationError, EmailDeliveryError
from app.routers import rooms as room_routes
from app.routers.rooms import router as rooms_router
from app.xiangqi import STARTING_FEN


@pytest.fixture
def rooms_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, fakeredis.FakeRedis]]:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(room_store, "redis_client", fake_redis)

    app = FastAPI()
    app.include_router(rooms_router, prefix="/api/v1/rooms")
    with TestClient(app) as client:
        yield client, fake_redis

    fake_redis.flushdb()


def _receive_socket_event(websocket: Any, event_type: str) -> dict[str, Any]:
    for _ in range(10):
        event = websocket.receive_json()
        if event.get("type") == event_type:
            return event
    raise AssertionError(f"Did not receive WebSocket event {event_type!r}")


def test_start_initializes_server_authoritative_board_and_clocks(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Timed room", "timer_seconds": 15},
    )
    host = created.json()
    client.post("/api/v1/rooms/1/join", json={})

    started = client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    snapshot = client.get("/api/v1/rooms/1/game")

    assert started.status_code == 200
    assert snapshot.status_code == 200
    game = snapshot.json()
    assert game["fen"] == STARTING_FEN
    assert game["version"] == 0
    assert game["side_to_move"] == "w"
    assert 0 < game["red_time_ms"] <= 15_000
    assert game["black_time_ms"] == 15_000
    assert game["timer_seconds"] == 15
    assert game["status"] == "playing"


def test_make_move_is_server_validated_and_broadcast_to_room(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Move sync", "timer_seconds": 60},
    )
    host = created.json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )

    red_ws_url = f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    black_ws_url = f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"
    with client.websocket_connect(red_ws_url) as red_ws:
        with client.websocket_connect(black_ws_url) as black_ws:
            red_snapshot = red_ws.receive_json()
            black_snapshot = black_ws.receive_json()
            assert red_snapshot["game"]["fen"] == STARTING_FEN
            assert black_snapshot["game"]["status"] == "playing"

            timer_event = _receive_socket_event(red_ws, "timer_tick")
            assert timer_event["side_to_move"] == "w"
            assert timer_event["red_time_ms"] <= 60_000

            black_ws.send_json(
                {"type": "make_move", "from": [0, 1], "to": [2, 0]}
            )
            rejected = _receive_socket_event(black_ws, "move_rejected")
            assert rejected["type"] == "move_rejected"
            assert rejected["reason"] == "not_your_turn"
            assert rejected["game"]["side_to_move"] == "w"

            red_ws.send_json(
                {"type": "make_move", "from": [9, 1], "to": [9, 2]}
            )
            illegal = _receive_socket_event(red_ws, "move_rejected")
            assert illegal["reason"] == "illegal_move"

            red_ws.send_json(
                {"type": "make_move", "from": [9, 1], "to": [7, 0]}
            )
            red_event = _receive_socket_event(red_ws, "move_made")
            black_event = _receive_socket_event(black_ws, "move_made")
            assert red_event["type"] == "move_made"
            assert black_event == red_event
            assert red_event["move"] == {"from": [9, 1], "to": [7, 0]}
            assert red_event["game"]["side_to_move"] == "b"
            assert red_event["game"]["version"] == 1
            assert red_event["game"]["fen"] != STARTING_FEN


def test_spectator_cannot_submit_a_move(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"name": "Spectator move"}).json()
    client.post("/api/v1/rooms/1/join", json={})
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    spectator = client.post("/api/v1/rooms/1/join", json={}).json()

    with client.websocket_connect(
        f"/api/v1/rooms/1/ws?participant_token={spectator['participant_token']}"
    ) as websocket:
        assert websocket.receive_json()["role"] == "spectator"
        websocket.send_json(
            {"type": "make_move", "from": [9, 1], "to": [7, 0]}
        )
        rejected = _receive_socket_event(websocket, "move_rejected")

    assert rejected == {
        "type": "move_rejected",
        "reason": "spectators_cannot_move",
    }


def test_authoritative_timer_finishes_game_when_active_clock_expires(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, fake_redis = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Timeout", "timer_seconds": 15},
    )
    host = created.json()
    client.post("/api/v1/rooms/1/join", json={})
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )

    with client.websocket_connect(
        f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    ) as websocket:
        assert websocket.receive_json()["game"]["status"] == "playing"
        seconds, microseconds = fake_redis.time()
        started_at_ms = int(seconds) * 1000 + int(microseconds) // 1000 - 16_000
        fake_redis.hset("room:1", "turn_started_at_ms", started_at_ms)

        timeout_event = _receive_socket_event(websocket, "game.timeout")
        final_state = client.get("/api/v1/rooms/1/game")
        assert final_state.status_code == 200
        assert final_state.json()["result"] == "timeout"

    assert timeout_event["game"]["status"] == "finished"
    assert timeout_event["game"]["result"] == "timeout"
    assert timeout_event["game"]["winner"] == "b"
    assert timeout_event["game"]["red_time_ms"] == 0


def test_public_room_roles_start_and_host_deletion(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client

    created = client.post(
        "/api/v1/rooms/",
        json={"name": "  Weekend game  ", "host_name": "  Minh Anh  "},
    )
    assert created.status_code == 201
    host = created.json()
    assert host["id"] == 1
    assert host["name"] == "Weekend game"
    assert host["host_name"] == "Minh Anh"
    assert host["visibility"] == "public"
    assert host["status"] == "waiting"
    assert host["role"] == "player1"
    invite_link = urlparse(host["join_url"])
    assert invite_link.path == "/room/1"
    invite_token = parse_qs(invite_link.query)["token"][0]
    assert len(invite_token) >= 32
    assert invite_token != host["participant_token"]
    assert room_store.is_valid_invite_token(1, invite_token)
    assert host["participant_token"]

    lobby = client.get("/api/v1/rooms/")
    assert lobby.status_code == 200
    assert [room["id"] for room in lobby.json()] == [1]

    too_early = client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    assert too_early.status_code == 409

    opponent_response = client.post(
        "/api/v1/rooms/1/join",
        json={},
    )
    opponent = opponent_response.json()
    assert opponent_response.status_code == 200
    assert opponent["role"] == "player2"
    assert opponent["player_count"] == 2

    spectator_response = client.post("/api/v1/rooms/1/join", json={})
    spectator = spectator_response.json()
    assert spectator_response.status_code == 200
    assert spectator["role"] == "spectator"
    assert spectator["spectator_count"] == 1

    forbidden_start = client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": opponent["participant_token"]},
    )
    assert forbidden_start.status_code == 403

    started = client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "playing"
    assert client.get("/api/v1/rooms/").json() == []

    late_join = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": invite_token},
    )
    assert late_join.status_code == 200
    assert late_join.json()["role"] == "spectator"

    closed = client.post(
        "/api/v1/rooms/1/leave",
        json={"participant_token": host["participant_token"]},
    )
    assert closed.status_code == 200
    assert closed.json()["room_deleted"] is True
    assert client.get("/api/v1/rooms/1").status_code == 404

    next_room = client.post("/api/v1/rooms/", json={"name": "Next game"})
    assert next_room.status_code == 201
    assert next_room.json()["id"] == 2
    assert next_room.json()["host_name"] == "Khách"


def test_invitation_link_joins_each_friend_with_a_separate_token(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post("/api/v1/rooms/", json={"name": "Invite link"})
    invite_token = parse_qs(urlparse(created.json()["join_url"]).query)["token"][0]

    player = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": invite_token},
    )
    spectator = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": invite_token},
    )

    assert player.status_code == 200
    assert player.json()["role"] == "player2"
    assert spectator.status_code == 200
    assert spectator.json()["role"] == "spectator"
    assert player.json()["participant_token"] != invite_token
    assert spectator.json()["participant_token"] != player.json()["participant_token"]


def test_invalid_invitation_token_does_not_join_room(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    client.post("/api/v1/rooms/", json={"name": "Protected link"})

    response = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": "invalid-invitation-token".ljust(32, "x")},
    )

    assert response.status_code == 403
    assert client.get("/api/v1/rooms/1").json()["player_count"] == 1


def test_lobby_manual_code_joins_the_selected_room(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    client.post("/api/v1/rooms/", json={"name": "Manual code"})

    response = client.post("/api/v1/rooms/join", json={"room_code": "1"})

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["role"] == "player2"


def test_lobby_manual_code_requires_numeric_input(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client

    response = client.post("/api/v1/rooms/join", json={"room_code": "room-one"})

    assert response.status_code == 422


def test_host_can_email_a_room_invitation(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = rooms_client
    created = client.post("/api/v1/rooms/", json={"name": "Email invite"})
    host = created.json()
    sent_messages: list[tuple[str, str, str, str]] = []
    monkeypatch.setattr(
        room_routes,
        "send_room_invitation_email",
        lambda recipient, room_name, room_code, join_url: sent_messages.append(
            (recipient, room_name, room_code, join_url)
        ),
    )

    response = client.post(
        "/api/v1/rooms/1/invite",
        json={
            "email": "friend@example.com",
            "participant_token": host["participant_token"],
        },
    )

    assert response.status_code == 202
    result = response.json()
    assert result["email"] == "friend@example.com"
    assert result["room_code"] == "1"
    assert result["join_url"] == host["join_url"]
    assert sent_messages == [
        ("friend@example.com", "Email invite", "1", host["join_url"])
    ]


def test_only_room_host_can_email_an_invitation(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = rooms_client
    client.post("/api/v1/rooms/", json={"name": "Host-only invite"})
    player = client.post("/api/v1/rooms/1/join", json={}).json()
    monkeypatch.setattr(room_routes, "send_room_invitation_email", lambda *_args: None)

    response = client.post(
        "/api/v1/rooms/1/invite",
        json={"email": "friend@example.com", "participant_token": player["participant_token"]},
    )

    assert response.status_code == 403


def test_invitation_delivery_failure_returns_service_unavailable(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"name": "SMTP failure"}).json()

    def fail_delivery(*_args: object, **_kwargs: object) -> None:
        raise EmailDeliveryError("SMTP unavailable")

    monkeypatch.setattr(room_routes, "send_room_invitation_email", fail_delivery)
    response = client.post(
        "/api/v1/rooms/1/invite",
        json={"email": "friend@example.com", "participant_token": host["participant_token"]},
    )

    assert response.status_code == 503


def test_unconfigured_smtp_returns_service_unavailable(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"name": "No SMTP"}).json()

    def fail_configuration(*_args: object, **_kwargs: object) -> None:
        raise EmailConfigurationError("SMTP is not configured")

    monkeypatch.setattr(room_routes, "send_room_invitation_email", fail_configuration)
    response = client.post(
        "/api/v1/rooms/1/invite",
        json={"email": "friend@example.com", "participant_token": host["participant_token"]},
    )

    assert response.status_code == 503


def test_room_invitation_email_includes_room_code_and_direct_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        email_service,
        "_send_email_message",
        lambda recipient, subject, body: sent_messages.append((recipient, subject, body)),
    )

    email_service.send_room_invitation_email(
        "friend@example.com",
        "Weekend game",
        "42",
        "https://game.example/room/42?token=secure-token",
    )

    assert len(sent_messages) == 1
    recipient, subject, body = sent_messages[0]
    assert recipient == "friend@example.com"
    assert "invited" in subject.lower()
    assert "Room code: 42" in body
    assert "https://game.example/room/42?token=secure-token" in body


def test_host_websocket_disconnect_deletes_room(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post("/api/v1/rooms/", json={"name": "Disconnect test"})
    room = created.json()

    with client.websocket_connect(
        f"/api/v1/rooms/{room['id']}/ws?participant_token={room['participant_token']}"
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "room.snapshot"
        assert snapshot["role"] == "player1"
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json() == {"type": "pong"}

    assert client.get(f"/api/v1/rooms/{room['id']}").status_code == 404


def test_lobby_socket_snapshots_waiting_rooms_and_hides_started_rooms(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Lobby test", "host_name": "Lobby Host"},
    )
    host = created.json()
    client.post("/api/v1/rooms/1/join", json={})

    with client.websocket_connect("/api/v1/rooms/ws") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "rooms.snapshot"
        assert len(snapshot["rooms"]) == 1
        room = snapshot["rooms"][0]
        assert room["id"] == 1
        assert room["name"] == "Lobby test"
        assert room["host_name"] == "Lobby Host"
        assert room["status"] == "waiting"
        assert room["player_count"] == 2
        assert room["spectator_count"] == 0
        assert isinstance(room["created_at"], int)

        started = client.post(
            "/api/v1/rooms/1/start",
            json={"participant_token": host["participant_token"]},
        )
        assert started.status_code == 200
        assert websocket.receive_json() == {
            "type": "room.removed",
            "room_id": 1,
            "reason": "started",
        }
        assert client.get("/api/v1/rooms/").json() == []
