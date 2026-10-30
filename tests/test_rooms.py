"""Tests for Redis-backed public room lifecycle and participant roles."""

from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import email_service, room_store
from app.email_service import EmailConfigurationError, EmailDeliveryError
from app.routers import rooms as room_routes
from app.routers.rooms import router as rooms_router
from app.security import verify_password
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


def _ready_player_two(client: TestClient, participant_token: str, room_id: int = 1) -> None:
    response = client.post(
        f"/api/v1/rooms/{room_id}/ready",
        json={"participant_token": participant_token, "ready": True},
    )
    assert response.status_code == 200, response.text


def test_start_initializes_server_authoritative_board_and_clocks(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Timed room", "timer_seconds": 15},
    )
    host = created.json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])

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
    _ready_player_two(client, opponent["participant_token"])
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
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
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
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
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
    _ready_player_two(client, opponent["participant_token"])

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


def test_lobby_socket_join_room_event_returns_the_assigned_role(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"room_name": "Socket join"}).json()

    with client.websocket_connect("/api/v1/rooms/ws") as websocket:
        assert websocket.receive_json()["type"] == "rooms.snapshot"
        websocket.send_json({"type": "join_room", "room_id": host["room_id"]})

        joined_event = None
        for _ in range(10):
            event = websocket.receive_json()
            if event.get("type") == "room.joined":
                joined_event = event
                break

        assert joined_event is not None
        access = joined_event["access"]
        assert access["role"] == "player2"
        assert access["room_id"] == host["room_id"]
        assert access["participant_token"]
        assert client.get("/api/v1/rooms/1").json()["player_count"] == 2


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


def test_player_two_must_be_ready_before_host_can_start(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"room_name": "Ready room"}).json()
    player_two = client.post("/api/v1/rooms/1/join", json={}).json()
    assert host["role"] == "player1"
    assert player_two["role"] == "player2"
    assert host["player2_ready"] is False

    host_url = f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    player_two_url = f"/api/v1/rooms/1/ws?participant_token={player_two['participant_token']}"
    with client.websocket_connect(host_url) as host_ws:
        assert host_ws.receive_json()["type"] == "room.snapshot"
        with client.websocket_connect(player_two_url) as player_two_ws:
            player_snapshot = player_two_ws.receive_json()
            assert player_snapshot["type"] == "room.snapshot"
            assert player_snapshot["role"] == "player2"

            host_ws.send_json({"type": "ready"})
            host_ready_error = host_ws.receive_json()
            assert host_ready_error["type"] == "error"
            assert host_ready_error["status"] == 403

            not_ready_start = client.post(
                "/api/v1/rooms/1/start",
                json={"participant_token": host["participant_token"]},
            )
            assert not_ready_start.status_code == 409
            assert not_ready_start.json()["detail"] == (
                "Player two must be ready before the game starts"
            )

            player_two_ws.send_json({"type": "ready", "ready": True})
            ready_event = _receive_socket_event(host_ws, "player.ready")
            assert ready_event["role"] == "player2"
            assert ready_event["room"]["player2_ready"] is True
            assert _receive_socket_event(player_two_ws, "player.ready") == ready_event

            player_two_ws.send_json({"type": "ready", "ready": False})
            unready_event = _receive_socket_event(host_ws, "player.ready")
            assert unready_event["ready"] is False
            assert unready_event["room"]["player2_ready"] is False
            assert _receive_socket_event(player_two_ws, "player.ready") == unready_event

            ready_response = client.post(
                "/api/v1/rooms/1/ready",
                json={"participant_token": player_two["participant_token"]},
            )
            assert ready_response.status_code == 200
            assert ready_response.json()["player2_ready"] is True
            assert _receive_socket_event(host_ws, "player.ready")["ready"] is True
            _receive_socket_event(player_two_ws, "player.ready")

            started = client.post(
                "/api/v1/rooms/1/start",
                json={"participant_token": host["participant_token"]},
            )
            assert started.status_code == 200
            assert started.json()["status"] == "playing"
            assert _receive_socket_event(host_ws, "room.started")["type"] == "room.started"
            assert _receive_socket_event(player_two_ws, "room.started")["type"] == "room.started"


def test_player_two_leaving_resets_readiness_for_the_next_opponent(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"room_name": "Ready reset"}).json()
    first_opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, first_opponent["participant_token"])

    left = client.post(
        "/api/v1/rooms/1/leave",
        json={"participant_token": first_opponent["participant_token"]},
    )
    assert left.status_code == 200
    after_leave = client.get("/api/v1/rooms/1").json()
    assert after_leave["player_count"] == 1
    assert after_leave["player2_ready"] is False

    next_opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    assert next_opponent["role"] == "player2"
    assert next_opponent["player2_ready"] is False
    not_ready_start = client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    assert not_ready_start.status_code == 409


def test_room_creation_accepts_lobby_options_and_generates_unique_ids(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, fake_redis = rooms_client
    password = "private-room-pass"

    private_room = client.post(
        "/api/v1/rooms/",
        json={
            "room_name": "Private match",
            "host_name": "Host",
            "time_per_move": 60,
            "is_public": False,
            "password": password,
            "allow_spectators": False,
        },
    )
    public_room = client.post(
        "/api/v1/rooms/",
        json={"name": "Legacy public match", "timer_seconds": 15},
    )

    assert private_room.status_code == 201
    assert public_room.status_code == 201
    private_data = private_room.json()
    public_data = public_room.json()
    assert private_data["room_id"] == private_data["id"] == 1
    assert public_data["room_id"] == public_data["id"] == 2
    assert private_data["room_uuid"] != public_data["room_uuid"]
    assert len(private_data["room_uuid"]) == 32
    assert UUID(hex=private_data["room_uuid"]).hex == private_data["room_uuid"]
    assert private_data["room_name"] == "Private match"
    assert private_data["time_per_move"] == 60
    assert private_data["visibility"] == "private"
    assert private_data["is_public"] is False
    assert private_data["has_password"] is True
    assert private_data["allow_spectators"] is False
    assert "password" not in private_data
    assert "password_hash" not in private_data
    stored_hash = fake_redis.hget("room:1", "password_hash")
    assert stored_hash != password
    assert verify_password(password, stored_hash)

    lobby = client.get("/api/v1/rooms/")
    assert [room["id"] for room in lobby.json()] == [2]
    assert lobby.json()[0]["time_per_move"] == 15


def test_password_protected_room_and_spectator_policy(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={
            "room_name": "Locked table",
            "is_public": True,
            "password": "room-password",
            "allow_spectators": False,
        },
    )
    invite_token = parse_qs(urlparse(created.json()["join_url"]).query)["token"][0]

    wrong_password = client.post(
        "/api/v1/rooms/1/join",
        json={"password": "wrong-password"},
    )
    first_player = client.post(
        "/api/v1/rooms/join",
        json={"room_code": "1", "password": "room-password"},
    )
    resumed_player = client.post(
        "/api/v1/rooms/1/join",
        json={"participant_token": first_player.json()["participant_token"]},
    )
    second_join = client.post(
        "/api/v1/rooms/1/join",
        json={"password": "room-password"},
    )

    assert wrong_password.status_code == 403
    assert first_player.status_code == 200
    assert first_player.json()["role"] == "player2"
    assert resumed_player.status_code == 200
    assert resumed_player.json()["role"] == "player2"
    assert second_join.status_code == 403
    assert second_join.json()["detail"] == "Spectators are not allowed in this room"
    assert client.get(
        "/api/v1/rooms/1",
        headers={"X-Room-Participant-Token": created.json()["participant_token"]},
    ).json()["spectator_count"] == 0

    host_token = created.json()["participant_token"]
    _ready_player_two(client, first_player.json()["participant_token"])
    assert client.post(
        "/api/v1/rooms/1/start", json={"participant_token": host_token}
    ).status_code == 200
    spectator_after_start = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": invite_token},
    )
    assert spectator_after_start.status_code == 403


def test_private_room_details_require_room_scoped_credentials(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    private_room = client.post(
        "/api/v1/rooms/",
        json={
            "room_name": "Private details",
            "is_public": False,
            "password": "correct-password",
        },
    ).json()
    other_room = client.post(
        "/api/v1/rooms/",
        json={"room_name": "Another room", "is_public": False},
    ).json()
    invite_token = parse_qs(urlparse(private_room["join_url"]).query)["token"][0]
    url = f"/api/v1/rooms/{private_room['room_id']}"

    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Room-Password": "wrong-password"}).status_code == 403
    assert client.get(
        url,
        headers={"X-Room-Participant-Token": other_room["participant_token"]},
    ).status_code == 403

    host_details = client.get(
        url,
        headers={"X-Room-Participant-Token": private_room["participant_token"]},
    )
    invite_details = client.get(
        url,
        headers={"X-Room-Invite-Token": invite_token},
    )
    password_details = client.get(url, headers={"X-Room-Password": "correct-password"})

    assert host_details.status_code == invite_details.status_code == password_details.status_code == 200
    assert host_details.json()["room_name"] == "Private details"
    assert "password" not in host_details.json()
    assert "password_hash" not in host_details.json()


def test_private_game_state_requires_access_and_respects_spectator_policy(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, fake_redis = rooms_client
    host = client.post(
        "/api/v1/rooms/",
        json={
            "room_name": "Private game state",
            "is_public": False,
            "password": "match-password",
            "allow_spectators": True,
        },
    ).json()
    invite_token = parse_qs(urlparse(host["join_url"]).query)["token"][0]
    opponent = client.post(
        f"/api/v1/rooms/{host['room_id']}/join",
        json={"password": "match-password"},
    ).json()
    _ready_player_two(client, opponent["participant_token"], host["room_id"])
    started = client.post(
        f"/api/v1/rooms/{host['room_id']}/start",
        json={"participant_token": host["participant_token"]},
    )
    assert started.status_code == 200

    url = f"/api/v1/rooms/{host['room_id']}/game"
    unauthenticated = client.get(url)
    assert unauthenticated.status_code == 401
    assert "fen" not in unauthenticated.json()
    assert client.get(
        url,
        headers={"X-Room-Participant-Token": host["participant_token"]},
    ).status_code == 200
    assert client.get(
        url,
        headers={"X-Room-Participant-Token": opponent["participant_token"]},
    ).status_code == 200
    assert client.get(
        url,
        headers={"X-Room-Invite-Token": invite_token},
    ).status_code == 200

    denied_host = client.post(
        "/api/v1/rooms/",
        json={
            "room_name": "No spectators",
            "is_public": False,
            "password": "closed-password",
            "allow_spectators": False,
        },
    ).json()
    denied_invite_token = parse_qs(urlparse(denied_host["join_url"]).query)["token"][0]
    denied_opponent = client.post(
        f"/api/v1/rooms/{denied_host['room_id']}/join",
        json={"password": "closed-password"},
    ).json()
    _ready_player_two(client, denied_opponent["participant_token"], denied_host["room_id"])
    assert client.post(
        f"/api/v1/rooms/{denied_host['room_id']}/start",
        json={"participant_token": denied_host["participant_token"]},
    ).status_code == 200

    denied_url = f"/api/v1/rooms/{denied_host['room_id']}/game"
    assert client.get(
        denied_url,
        headers={"X-Room-Invite-Token": denied_invite_token},
    ).status_code == 403
    assert client.get(
        denied_url,
        headers={"X-Room-Password": "closed-password"},
    ).status_code == 403

    forged_spectator_token = "spectator-token-that-is-not-issued-0001"
    fake_redis.hset("room:2:participants", forged_spectator_token, "spectator")
    assert client.get(
        denied_url,
        headers={"X-Room-Participant-Token": forged_spectator_token},
    ).status_code == 403
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(
            f"/api/v1/rooms/{denied_host['room_id']}/ws?participant_token={forged_spectator_token}"
        ):
            pass
    assert closed.value.code == 4403


def test_leaving_participant_socket_is_revoked_before_future_room_events(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post(
        "/api/v1/rooms/",
        json={"room_name": "Socket revocation", "is_public": False},
    ).json()
    opponent = client.post(
        f"/api/v1/rooms/{host['room_id']}/join",
        json={"invite_token": parse_qs(urlparse(host["join_url"]).query)["token"][0]},
    ).json()

    with client.websocket_connect(
        f"/api/v1/rooms/{host['room_id']}/ws?participant_token={host['participant_token']}"
    ) as host_ws:
        with client.websocket_connect(
            f"/api/v1/rooms/{host['room_id']}/ws?participant_token={opponent['participant_token']}"
        ) as opponent_ws:
            assert host_ws.receive_json()["type"] == "room.snapshot"
            assert opponent_ws.receive_json()["type"] == "room.snapshot"

            left = client.post(
                f"/api/v1/rooms/{host['room_id']}/leave",
                json={"participant_token": opponent["participant_token"]},
            )

            assert left.status_code == 200
            assert _receive_socket_event(host_ws, "room.participant_left")["room"]["player_count"] == 1
            with pytest.raises(WebSocketDisconnect) as closed:
                opponent_ws.receive_json()
            assert closed.value.code == 4403


def test_private_room_without_password_requires_invitation_token(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"room_name": "Invite-only table", "is_public": False},
    )
    invite_token = parse_qs(urlparse(created.json()["join_url"]).query)["token"][0]

    denied = client.post("/api/v1/rooms/1/join", json={})
    joined = client.post(
        "/api/v1/rooms/1/join",
        json={"invite_token": invite_token},
    )

    assert created.status_code == 201
    assert client.get("/api/v1/rooms/").json() == []
    assert denied.status_code == 403
    assert joined.status_code == 200
    assert joined.json()["role"] == "player2"


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


def test_waiting_host_disconnect_notifies_players_and_spectators(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post("/api/v1/rooms/", json={"name": "Waiting disconnect"}).json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    spectator = client.post("/api/v1/rooms/1/join", json={}).json()

    with client.websocket_connect("/api/v1/rooms/ws") as lobby_ws:
        assert lobby_ws.receive_json()["type"] == "rooms.snapshot"
        with client.websocket_connect(
            f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"
        ) as opponent_ws:
            assert opponent_ws.receive_json()["type"] == "room.snapshot"
            with client.websocket_connect(
                f"/api/v1/rooms/1/ws?participant_token={spectator['participant_token']}"
            ) as spectator_ws:
                assert spectator_ws.receive_json()["type"] == "room.snapshot"
                with client.websocket_connect(
                    f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
                ) as host_ws:
                    assert host_ws.receive_json()["type"] == "room.snapshot"

                assert _receive_socket_event(lobby_ws, "room.removed")["reason"] == "host_left"
                assert _receive_socket_event(opponent_ws, "room.closed")["room_id"] == 1
                assert _receive_socket_event(spectator_ws, "room.closed")["room_id"] == 1

    assert client.get("/api/v1/rooms/1").status_code == 404


def test_disconnected_player_can_reconnect_and_resume_game_clock(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post(
        "/api/v1/rooms/",
        json={"name": "Reconnect test", "timer_seconds": 60},
    ).json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    host_url = f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    opponent_url = f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"

    with client.websocket_connect(host_url) as host_ws:
        assert host_ws.receive_json()["type"] == "room.snapshot"
        with client.websocket_connect(opponent_url) as opponent_ws:
            assert opponent_ws.receive_json()["type"] == "room.snapshot"

        disconnected = _receive_socket_event(host_ws, "player.disconnected")
        assert disconnected["role"] == "player2"
        assert disconnected["reconnect_seconds"] == 60
        paused_game = client.get("/api/v1/rooms/1/game").json()
        assert paused_game["paused"] is True
        assert paused_game["disconnected_players"] == ["player2"]
        host_ws.send_json({"type": "make_move", "from": [9, 1], "to": [7, 0]})
        paused_move = _receive_socket_event(host_ws, "move_rejected")
        assert paused_move["reason"] == "player_disconnected"

        with client.websocket_connect(opponent_url) as reconnected_ws:
            snapshot = reconnected_ws.receive_json()
            assert snapshot["type"] == "room.snapshot"
            assert snapshot["game"]["paused"] is False
            assert snapshot["game"]["disconnected_players"] == []
            assert _receive_socket_event(host_ws, "player.reconnected")["role"] == "player2"
            assert _receive_socket_event(reconnected_ws, "player.reconnected")["role"] == "player2"

            left = client.post(
                "/api/v1/rooms/1/leave",
                json={"participant_token": host["participant_token"]},
            )
            assert left.status_code == 200
            assert _receive_socket_event(host_ws, "game.forfeit")["game"]["winner"] == "b"
            assert _receive_socket_event(reconnected_ws, "game.forfeit")["game"]["winner"] == "b"
            assert _receive_socket_event(host_ws, "room.closed")["reason"] == "host_forfeit"
            assert _receive_socket_event(reconnected_ws, "room.closed")["reason"] == "host_forfeit"


def test_one_of_multiple_host_sockets_dropping_does_not_start_reconnect_window(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post(
        "/api/v1/rooms/",
        json={"name": "Multiple sockets", "timer_seconds": 60},
    ).json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )
    host_url = f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    opponent_url = f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"

    with client.websocket_connect(opponent_url) as opponent_ws:
        assert opponent_ws.receive_json()["type"] == "room.snapshot"
        with client.websocket_connect(host_url) as second_host_ws:
            assert second_host_ws.receive_json()["type"] == "room.snapshot"
            with client.websocket_connect(host_url) as first_host_ws:
                assert first_host_ws.receive_json()["type"] == "room.snapshot"

            game = client.get("/api/v1/rooms/1/game").json()
            assert game["paused"] is False
            assert game["disconnected_players"] == []

            response = client.post(
                "/api/v1/rooms/1/leave",
                json={"participant_token": host["participant_token"]},
            )
            assert response.status_code == 200
            assert _receive_socket_event(second_host_ws, "game.forfeit")["game"]["winner"] == "b"
            assert _receive_socket_event(opponent_ws, "game.forfeit")["game"]["winner"] == "b"


def test_reconnect_timeout_forfeits_disconnected_player(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = rooms_client
    monkeypatch.setattr(room_store, "RECONNECT_TIMEOUT_MS", 20)
    host = client.post(
        "/api/v1/rooms/",
        json={"name": "Reconnect timeout", "timer_seconds": 60},
    ).json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )

    with client.websocket_connect(
        f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    ) as host_ws:
        assert host_ws.receive_json()["type"] == "room.snapshot"
        with client.websocket_connect(
            f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"
        ) as opponent_ws:
            assert opponent_ws.receive_json()["type"] == "room.snapshot"

        disconnected = _receive_socket_event(host_ws, "player.disconnected")
        assert disconnected["role"] == "player2"
        result = _receive_socket_event(host_ws, "game.forfeit")
        assert result["reason"] == "reconnect_timeout"
        assert result["loser_role"] == "player2"
        assert result["game"]["result"] == "forfeit"
        assert result["game"]["winner"] == "w"
        state = client.get("/api/v1/rooms/1/game").json()
        assert state["status"] == "finished"
        assert state["result"] == "forfeit"
        assert state["winner"] == "w"


def test_host_voluntary_exit_forfeits_then_deletes_playing_room(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    host = client.post(
        "/api/v1/rooms/",
        json={"name": "Host forfeit", "timer_seconds": 60},
    ).json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])
    client.post(
        "/api/v1/rooms/1/start",
        json={"participant_token": host["participant_token"]},
    )

    with client.websocket_connect(
        f"/api/v1/rooms/1/ws?participant_token={host['participant_token']}"
    ) as host_ws:
        assert host_ws.receive_json()["type"] == "room.snapshot"
        with client.websocket_connect(
            f"/api/v1/rooms/1/ws?participant_token={opponent['participant_token']}"
        ) as opponent_ws:
            assert opponent_ws.receive_json()["type"] == "room.snapshot"
            response = client.post(
                "/api/v1/rooms/1/leave",
                json={"participant_token": host["participant_token"]},
            )
            assert response.status_code == 200
            assert response.json()["room_deleted"] is True

            host_result = _receive_socket_event(host_ws, "game.forfeit")
            opponent_result = _receive_socket_event(opponent_ws, "game.forfeit")
            assert host_result == opponent_result
            assert host_result["reason"] == "player_left"
            assert host_result["loser_role"] == "player1"
            assert host_result["game"]["result"] == "forfeit"
            assert host_result["game"]["winner"] == "b"
            assert _receive_socket_event(host_ws, "room.closed")["reason"] == "host_forfeit"
            assert _receive_socket_event(opponent_ws, "room.closed")["reason"] == "host_forfeit"

    assert client.get("/api/v1/rooms/1").status_code == 404


def test_lobby_socket_snapshots_waiting_rooms_and_hides_started_rooms(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client
    created = client.post(
        "/api/v1/rooms/",
        json={"name": "Lobby test", "host_name": "Lobby Host"},
    )
    host = created.json()
    opponent = client.post("/api/v1/rooms/1/join", json={}).json()
    _ready_player_two(client, opponent["participant_token"])

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
