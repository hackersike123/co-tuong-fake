"""Integration test for room lifecycle against the configured Redis server."""

from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from app import room_store


def test_public_room_lifecycle_uses_configured_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    prefix = f"test:rooms:{namespace}"
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(
        room_store,
        "_room_key",
        lambda room_id: f"{prefix}:room:{room_id}",
    )
    monkeypatch.setattr(
        room_store,
        "_participants_key",
        lambda room_id: f"{prefix}:room:{room_id}:participants",
    )
    monkeypatch.setattr(
        room_store,
        "_spectators_key",
        lambda room_id: f"{prefix}:room:{room_id}:spectators",
    )

    try:
        room, host_token = room_store.create_room("Redis integration room")
        room_id = room["id"]
        assert room_id == 1
        assert room["player_count"] == 1
        assert room_store.list_public_rooms()[0]["id"] == room_id

        assert room_store.join_room(room_id, "opponent-token") == "player2"
        assert room_store.join_room(room_id, "spectator-token") == "spectator"
        assert room_store.get_room(room_id)["player_count"] == 2
        assert room_store.get_room(room_id)["spectator_count"] == 1

        assert room_store.start_room(room_id, host_token) == 1
        assert room_store.list_public_rooms() == []
        assert room_store.get_room(room_id)["status"] == "playing"

        assert room_store.join_room(room_id, "late-spectator-token") == "spectator"
        assert room_store.leave_room(room_id, host_token) == 2
        assert room_store.get_room(room_id) is None
        assert room_store.list_public_rooms() == []
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)
