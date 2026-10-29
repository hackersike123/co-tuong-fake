"""Integration test for room lifecycle against the configured Redis server."""

from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from app import room_store
from app.xiangqi import Move, XiangqiState, apply_move


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


def test_live_game_moves_and_timeout_use_redis_server_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    prefix = f"test:room-game:{namespace}"
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(room_store, "_room_key", lambda room_id: f"{prefix}:room:{room_id}")
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
        room, host_token = room_store.create_room("Timer integration", timer_seconds=15)
        room_id = room["id"]
        assert room_store.join_room(room_id, "opponent-token") == "player2"
        assert room_store.start_room(room_id, host_token) == 1

        initial_snapshot = room_store.get_game_snapshot(room_id)
        assert initial_snapshot is not None
        assert initial_snapshot["red_time_ms"] <= 15_000
        assert initial_snapshot["black_time_ms"] == 15_000

        state = XiangqiState.from_fen(initial_snapshot["fen"])
        next_state = apply_move(state, Move((9, 1), (7, 0)))
        applied = room_store.apply_game_move(
            room_id,
            initial_snapshot["version"],
            initial_snapshot["fen"],
            "w",
            next_state.turn.value,
            next_state.to_fen(),
        )
        assert applied == 1

        after_move = room_store.get_game_snapshot(room_id)
        assert after_move is not None
        assert after_move["version"] == 1
        assert after_move["side_to_move"] == "b"
        assert after_move["fen"] == next_state.to_fen()
        assert after_move["red_time_ms"] < 15_000

        stale_move = room_store.apply_game_move(
            room_id,
            initial_snapshot["version"],
            initial_snapshot["fen"],
            "w",
            next_state.turn.value,
            next_state.to_fen(),
        )
        assert stale_move == -2

        redis_seconds, redis_microseconds = room_store.redis_client.time()
        past_start_ms = int(redis_seconds) * 1000 + int(redis_microseconds) // 1000 - 20_000
        room_store.redis_client.hset(
            room_store._room_key(room_id),
            "turn_started_at_ms",
            past_start_ms,
        )
        assert room_store.timeout_room(room_id, after_move["version"])

        finished = room_store.get_game_snapshot(room_id)
        assert finished is not None
        assert finished["status"] == "finished"
        assert finished["result"] == "timeout"
        assert finished["winner"] == "w"
        assert finished["black_time_ms"] == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)
