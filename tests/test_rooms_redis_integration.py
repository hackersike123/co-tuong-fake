"""Integration test for room lifecycle against the configured Redis server."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from redis.exceptions import RedisError

from app import room_store
from app.xiangqi import Move, XiangqiState, apply_move


@pytest.fixture(autouse=True)
def isolate_room_auxiliary_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    prefix = f"test:room-aux:{uuid4().hex}"
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(
        room_store,
        "_chat_history_key",
        lambda room_id: f"{prefix}:chat:{room_id}",
    )
    monkeypatch.setattr(
        room_store,
        "_room_code_key",
        lambda room_code: f"{prefix}:code:{room_code}",
    )


def _isolate_room_store_for_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    prefix: str,
) -> None:
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
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
    monkeypatch.setattr(
        room_store,
        "_chat_history_key",
        lambda room_id: f"{prefix}:room:{room_id}:chat",
    )
    monkeypatch.setattr(
        room_store,
        "_room_code_key",
        lambda room_code: f"{prefix}:code:{room_code}",
    )


def _delete_room_during_legacy_field_write(
    monkeypatch: pytest.MonkeyPatch,
    room_id: int,
    host_token: str,
    field: str,
) -> list[int]:
    room_key = room_store._room_key(room_id)
    deletions: list[int] = []
    delete_once = False
    original_hsetnx = room_store.redis_client.hsetnx
    original_eval = room_store.redis_client.eval

    def delete_room_once() -> None:
        nonlocal delete_once
        if not delete_once:
            delete_once = True
            deletions.append(room_store.leave_room(room_id, host_token))

    def hsetnx(key: str, field_name: str, value: str):
        if key == room_key and field_name == field:
            delete_room_once()
        return original_hsetnx(key, field_name, value)

    def evaluate(script, numkeys, *keys_and_args, **kwargs):
        legacy_field_write = (
            numkeys == 1
            and keys_and_args[0] == room_key
            and len(keys_and_args) > 1
            and keys_and_args[1] == field
        )
        room_code_write = (
            field == "room_code"
            and numkeys == 2
            and len(keys_and_args) >= 4
            and keys_and_args[0] == room_key
            and keys_and_args[1]
            == room_store._room_code_key(str(keys_and_args[3]))
        )
        if legacy_field_write or room_code_write:
            delete_room_once()
        return original_eval(script, numkeys, *keys_and_args, **kwargs)

    monkeypatch.setattr(room_store.redis_client, "hsetnx", hsetnx)
    monkeypatch.setattr(room_store.redis_client, "eval", evaluate)
    return deletions


def test_legacy_room_code_migration_cannot_recreate_a_deleted_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-code-delete-race:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Legacy room-code migration")
        room_id = room["id"]
        room_store.redis_client.hdel(room_store._room_key(room_id), "room_code")
        room_store.redis_client.delete(room_store._room_code_key(room["room_code"]))
        room_store.append_chat_message(room_id, {"id": "legacy-chat", "text": "private"})
        chat_key = room_store._chat_history_key(room_id)
        deletions = _delete_room_during_legacy_field_write(
            monkeypatch,
            room_id,
            host_token,
            "room_code",
        )
        migrated = room_store.get_room(room_id)

        assert migrated is None
        assert deletions == [2]
        assert room_store.redis_client.exists(room_store._room_key(room_id)) == 0
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(
            room_store._room_code_key(room["room_code"])
        ) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_room_uuid_migration_cannot_recreate_a_deleted_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-uuid-delete-race:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Legacy room UUID")
        room_id = room["id"]
        room_store.redis_client.hdel(room_store._room_key(room_id), "room_uuid")
        room_store.append_chat_message(room_id, {"id": "uuid-chat", "text": "private"})
        chat_key = room_store._chat_history_key(room_id)
        code_key = room_store._room_code_key(room["room_code"])
        deletions = _delete_room_during_legacy_field_write(
            monkeypatch,
            room_id,
            host_token,
            "room_uuid",
        )

        assert room_store.get_room(room_id) is None

        assert deletions == [2]
        assert room_store.redis_client.exists(room_store._room_key(room_id)) == 0
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(code_key) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_invite_token_migration_cannot_recreate_a_deleted_room(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-invite-delete-race:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Legacy room invite")
        room_id = room["id"]
        room_store.redis_client.hdel(room_store._room_key(room_id), "invite_token")
        room_store.append_chat_message(room_id, {"id": "invite-chat", "text": "private"})
        chat_key = room_store._chat_history_key(room_id)
        code_key = room_store._room_code_key(room["room_code"])
        deletions = _delete_room_during_legacy_field_write(
            monkeypatch,
            room_id,
            host_token,
            "invite_token",
        )

        assert room_store.get_or_create_invite_token(room_id) is None

        assert deletions == [2]
        assert room_store.redis_client.exists(room_store._room_key(room_id)) == 0
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(code_key) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_host_leave_removes_chat_history_and_room_code_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-host-leave-cleanup:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Host leave cleanup", is_public=False)
        room_id = room["id"]
        room_code = room["room_code"]
        room_store.append_chat_message(room_id, {"id": "cleanup-chat", "text": "private"})

        chat_key = room_store._chat_history_key(room_id)
        code_key = room_store._room_code_key(room_code)
        assert room_store.redis_client.exists(chat_key) == 1
        assert room_store.redis_client.exists(code_key) == 1

        assert room_store.leave_room(room_id, host_token) == 2

        assert room_store.get_room(room_id) is None
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(code_key) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_host_disconnect_from_waiting_room_removes_auxiliary_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-host-disconnect-cleanup:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Host disconnect cleanup", is_public=False)
        room_id = room["id"]
        room_code = room["room_code"]
        room_store.append_chat_message(room_id, {"id": "disconnect-chat", "text": "private"})
        chat_key = room_store._chat_history_key(room_id)
        code_key = room_store._room_code_key(room_code)

        disconnected = room_store.mark_player_disconnected(room_id, host_token)

        assert disconnected["code"] == 2
        assert room_store.get_room(room_id) is None
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(code_key) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_host_disconnect_from_finished_room_removes_auxiliary_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    prefix = f"test:room-finished-host-cleanup:{uuid4().hex}"
    _isolate_room_store_for_cleanup(monkeypatch, prefix)
    try:
        room, host_token = room_store.create_room("Finished host cleanup")
        room_id = room["id"]
        room_code = room["room_code"]
        opponent_token = "finished-room-opponent"
        assert room_store.join_room(room_id, opponent_token) == "player2"
        assert room_store.set_player_ready(room_id, opponent_token) == 1
        assert room_store.start_room(room_id, host_token) == 1
        room_store.append_chat_message(room_id, {"id": "finished-chat", "text": "private"})
        chat_key = room_store._chat_history_key(room_id)
        code_key = room_store._room_code_key(room_code)
        assert room_store.leave_room(room_id, opponent_token) == 5

        disconnected = room_store.mark_player_disconnected(room_id, host_token)

        assert disconnected["code"] == 2
        assert room_store.get_room(room_id) is None
        assert room_store.redis_client.exists(chat_key) == 0
        assert room_store.redis_client.exists(code_key) == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


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
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(
        room_store,
        "_room_key",
        lambda room_id: f"{prefix}:room:{room_id}",
    )
    monkeypatch.setattr(room_store, "_room_code_key", lambda code: f"{prefix}:code:{code}")
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
        room_code = room["room_code"]
        assert room_id == 1
        assert room["room_id"] == room_id
        assert room_store.get_room_id_by_code(room_code) == room_id
        assert room["player_count"] == 1
        assert room_store.list_public_rooms()[0]["id"] == room_id

        assert room_store.join_room(room_id, "opponent-token") == "player2"
        assert room_store.set_player_ready(room_id, "opponent-token") == 1
        assert room_store.join_room(room_id, "spectator-token") == "spectator"
        assert room_store.get_room(room_id)["player_count"] == 2
        assert room_store.get_room(room_id)["spectator_count"] == 1

        assert room_store.start_room(room_id, host_token) == 1
        assert room_store.list_public_rooms() == []
        assert room_store.get_room(room_id)["status"] == "playing"

        assert room_store.join_room(room_id, "late-spectator-token") == "spectator"
        assert room_store.leave_room(room_id, host_token) == 4
        forfeited = room_store.get_game_snapshot(room_id)
        assert forfeited is not None
        assert forfeited["status"] == "finished"
        assert forfeited["result"] == "forfeit"
        assert forfeited["winner"] == "b"
        assert room_store.delete_room(room_id)
        assert room_store.get_room(room_id) is None
        assert room_store.get_room_id_by_code(room_code) is None
        assert room_store.list_public_rooms() == []

        private_room, _ = room_store.create_room(
            "Private Redis room",
            is_public=False,
            password_hash="hashed-room-password",
            allow_spectators=False,
        )
        private_room_id = private_room["id"]
        assert private_room_id == 2
        assert private_room["room_id"] == private_room_id
        assert private_room["room_uuid"] != room["room_uuid"]
        assert private_room["visibility"] == "private"
        assert private_room["has_password"] is True
        assert room_store.list_public_rooms() == []
        assert room_store.join_room(private_room_id, "private-opponent") == "player2"
        assert (
            room_store.join_room(private_room_id, "blocked-spectator")
            == "spectators_disabled"
        )
        assert room_store.get_room(private_room_id)["spectator_count"] == 0
        assert room_store.delete_room(private_room_id)

        race_room, _ = room_store.create_room("Concurrent joins")
        race_room_id = race_room["id"]
        tokens = [f"concurrent-token-{index}" for index in range(8)]
        with ThreadPoolExecutor(max_workers=len(tokens)) as executor:
            roles = list(
                executor.map(
                    lambda token: room_store.join_room(race_room_id, token),
                    tokens,
                )
            )
        assert roles.count("player2") == 1
        assert roles.count("spectator") == len(tokens) - 1
        assert room_store.get_room(race_room_id)["player_count"] == 2
        assert room_store.get_room(race_room_id)["spectator_count"] == len(tokens) - 1
        assert room_store.delete_room(race_room_id)
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_reconnect_grace_period_and_forfeit_use_redis_server_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    prefix = f"test:room-reconnect:{namespace}"
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(room_store, "_room_key", lambda room_id: f"{prefix}:room:{room_id}")
    monkeypatch.setattr(room_store, "_room_code_key", lambda code: f"{prefix}:code:{code}")
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
        room, host_token = room_store.create_room("Reconnect integration")
        room_id = room["id"]
        assert room_store.join_room(room_id, "opponent-token") == "player2"
        assert room_store.set_player_ready(room_id, "opponent-token") == 1
        assert room_store.start_room(room_id, host_token) == 1

        dropped = room_store.mark_player_disconnected(room_id, host_token)
        assert dropped["code"] == 3
        assert dropped["role"] == "player1"
        assert 0 < dropped["delay_ms"] <= room_store.RECONNECT_TIMEOUT_MS
        paused = room_store.get_game_snapshot(room_id)
        assert paused is not None
        assert paused["paused"] is True
        assert paused["disconnected_players"] == ["player1"]

        redis_seconds, redis_microseconds = room_store.redis_client.time()
        expired_deadline_ms = (
            int(redis_seconds) * 1000 + int(redis_microseconds) // 1000 - 1
        )
        room_store.redis_client.hset(
            room_store._room_key(room_id),
            "player1_reconnect_deadline_ms",
            expired_deadline_ms,
        )
        assert room_store.finalize_reconnect_forfeit(
            room_id,
            "player1",
            expired_deadline_ms,
        ) == 1

        finished = room_store.get_game_snapshot(room_id)
        assert finished is not None
        assert finished["status"] == "finished"
        assert finished["result"] == "forfeit"
        assert finished["winner"] == "b"
        assert room_store.mark_player_reconnected(room_id, "player1", host_token) == -4
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_timer_lease_allows_only_one_worker_to_broadcast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    prefix = f"test:room-timer-lease:{namespace}"
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(room_store, "_room_key", lambda room_id: f"{prefix}:room:{room_id}")
    monkeypatch.setattr(room_store, "_room_code_key", lambda code: f"{prefix}:code:{code}")
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
        room, host_token = room_store.create_room("Timer lease integration")
        room_id = room["id"]
        assert room_store.join_room(room_id, "opponent-token") == "player2"
        assert room_store.set_player_ready(room_id, "opponent-token") == 1
        assert room_store.start_room(room_id, host_token) == 1

        assert room_store.acquire_room_timer_lease(room_id, "worker-a") is True
        assert room_store.acquire_room_timer_lease(room_id, "worker-b") is False
        assert room_store.release_room_timer_lease(room_id, "worker-b") is False
        assert room_store.release_room_timer_lease(room_id, "worker-a") is True
        assert room_store.acquire_room_timer_lease(room_id, "worker-b") is True
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
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(room_store, "_room_key", lambda room_id: f"{prefix}:room:{room_id}")
    monkeypatch.setattr(room_store, "_room_code_key", lambda code: f"{prefix}:code:{code}")
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
        assert room_store.set_player_ready(room_id, "opponent-token") == 1
        assert room_store.start_room(room_id, host_token) == 1

        initial_snapshot = room_store.get_game_snapshot(room_id)
        assert initial_snapshot is not None
        assert initial_snapshot["red_time_ms"] <= 15_000
        assert initial_snapshot["black_time_ms"] == 15_000

        redis_seconds, redis_microseconds = room_store.redis_client.time()
        past_start_ms = int(redis_seconds) * 1000 + int(redis_microseconds) // 1000 - 5_000
        room_store.redis_client.hset(
            room_store._room_key(room_id),
            "turn_started_at_ms",
            past_start_ms,
        )
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
        assert after_move["red_time_ms"] < 11_000

        black_state = XiangqiState.from_fen(after_move["fen"])
        black_next_state = apply_move(black_state, Move((0, 1), (2, 0)))
        redis_seconds, redis_microseconds = room_store.redis_client.time()
        past_start_ms = int(redis_seconds) * 1000 + int(redis_microseconds) // 1000 - 5_000
        room_store.redis_client.hset(
            room_store._room_key(room_id),
            "turn_started_at_ms",
            past_start_ms,
        )
        assert room_store.apply_game_move(
            room_id,
            after_move["version"],
            after_move["fen"],
            "b",
            black_next_state.turn.value,
            black_next_state.to_fen(),
        ) == 1

        after_reply = room_store.get_game_snapshot(room_id)
        assert after_reply is not None
        assert after_reply["version"] == 2
        assert after_reply["side_to_move"] == "w"
        assert after_reply["red_time_ms"] > 14_900
        assert after_reply["black_time_ms"] < 11_000

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
        assert room_store.timeout_room(room_id, after_reply["version"])

        finished = room_store.get_game_snapshot(room_id)
        assert finished is not None
        assert finished["status"] == "finished"
        assert finished["result"] == "timeout"
        assert finished["winner"] == "b"
        assert finished["red_time_ms"] == 0
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)


def test_draw_resignation_notation_and_rematch_scripts_use_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    namespace = uuid4().hex
    prefix = f"test:room-results:{namespace}"
    monkeypatch.setattr(room_store, "PUBLIC_ROOMS_KEY", f"{prefix}:public")
    monkeypatch.setattr(room_store, "ROOM_SEQUENCE_KEY", f"{prefix}:sequence")
    monkeypatch.setattr(room_store, "ROOM_CODE_INDEX_PREFIX", f"{prefix}:code:")
    monkeypatch.setattr(room_store, "_room_key", lambda room_id: f"{prefix}:room:{room_id}")
    monkeypatch.setattr(room_store, "_room_code_key", lambda code: f"{prefix}:code:{code}")
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
        room, host_token = room_store.create_room("Results integration", timer_seconds=60)
        room_id = room["id"]
        opponent_token = f"opponent-{namespace}"
        assert room_store.join_room(room_id, opponent_token) == "player2"
        assert room_store.set_player_ready(room_id, opponent_token) == 1
        assert room_store.start_room(room_id, host_token) == 1

        initial = room_store.get_game_snapshot(room_id)
        assert initial is not None
        next_state = apply_move(
            XiangqiState.from_fen(initial["fen"]),
            Move((9, 1), (7, 0)),
        )
        assert room_store.apply_game_move(
            room_id,
            initial["version"],
            initial["fen"],
            "w",
            next_state.turn.value,
            next_state.to_fen(),
            notation="1. b9-a7",
        ) == 1
        assert room_store.get_game_snapshot(room_id)["notation"] == "1. b9-a7"

        assert room_store.offer_draw(room_id, host_token, "player1") == 1
        assert room_store.respond_to_draw(room_id, opponent_token, "player2", False) == 1
        assert room_store.offer_draw(room_id, host_token, "player1") == 1
        assert room_store.respond_to_draw(room_id, opponent_token, "player2", True) == 2
        agreed = room_store.get_game_snapshot(room_id)
        assert agreed is not None
        assert agreed["result"] == "agreement"
        assert agreed["winner"] is None

        assert room_store.request_rematch(room_id, host_token, "player1") == 1
        assert room_store.request_rematch(room_id, opponent_token, "player2") == 2
        assert room_store.get_room(room_id)["status"] == "waiting"
        assert room_store.set_player_ready(room_id, opponent_token) == 1
        assert room_store.start_room(room_id, host_token) == 1
        assert room_store.get_game_snapshot(room_id)["round_number"] == 2
        assert room_store.resign_game(room_id, opponent_token, "player2") == 1
        resigned = room_store.get_game_snapshot(room_id)
        assert resigned is not None
        assert resigned["result"] == "resignation"
        assert resigned["winner"] == "w"
    finally:
        for key in room_store.redis_client.scan_iter(match=f"{prefix}:*"):
            room_store.redis_client.delete(key)
