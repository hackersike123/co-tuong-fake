"""Tests for Redis-backed public room lifecycle and participant roles."""

from collections.abc import Iterator

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import room_store
from app.routers.rooms import router as rooms_router


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


def test_public_room_roles_start_and_host_deletion(
    rooms_client: tuple[TestClient, fakeredis.FakeRedis],
) -> None:
    client, _ = rooms_client

    created = client.post("/api/v1/rooms/", json={"name": "  Weekend game  "})
    assert created.status_code == 201
    host = created.json()
    assert host["id"] == 1
    assert host["name"] == "Weekend game"
    assert host["visibility"] == "public"
    assert host["status"] == "waiting"
    assert host["role"] == "player1"
    assert host["join_url"].endswith("/rooms/1")
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

    late_join = client.post("/api/v1/rooms/1/join", json={})
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
