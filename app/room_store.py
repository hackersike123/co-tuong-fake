"""Redis-backed storage and atomic lifecycle operations for public rooms."""

import secrets
import time
from typing import Any

from redis import Redis

from .settings import REDIS_URL
from .xiangqi import STARTING_FEN


redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=5,
)

PUBLIC_ROOMS_KEY = "rooms:public"
ROOM_SEQUENCE_KEY = "rooms:sequence"

_JOIN_ROOM_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
local existing_role = redis.call('HGET', KEYS[2], ARGV[1])
if existing_role then
    return existing_role
end
local status = redis.call('HGET', KEYS[1], 'status')
if status == 'waiting' then
    local player2_token = redis.call('HGET', KEYS[1], 'player2_token')
    if not player2_token or player2_token == '' then
        redis.call('HSET', KEYS[1], 'player2_token', ARGV[1])
        redis.call('HSET', KEYS[2], ARGV[1], 'player2')
        return 'player2'
    end
end
redis.call('HSET', KEYS[2], ARGV[1], 'spectator')
redis.call('SADD', KEYS[3], ARGV[1])
return 'spectator'
"""

_START_ROOM_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
if redis.call('HGET', KEYS[1], 'host_token') ~= ARGV[1] then
    return -2
end
if redis.call('HGET', KEYS[1], 'status') ~= 'waiting' then
    return -3
end
local player2_token = redis.call('HGET', KEYS[1], 'player2_token')
if not player2_token or player2_token == '' then
    return -4
end
local timer_seconds = tonumber(redis.call('HGET', KEYS[1], 'timer_seconds') or '30')
local redis_time = redis.call('TIME')
local now_ms = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
redis.call('HSET', KEYS[1],
    'status', 'playing',
    'game_fen', ARGV[3],
    'game_version', 0,
    'side_to_move', 'w',
    'red_time_ms', timer_seconds * 1000,
    'black_time_ms', timer_seconds * 1000,
    'turn_started_at_ms', now_ms,
    'game_result', '',
    'game_winner', '')
redis.call('ZREM', KEYS[2], ARGV[2])
return 1
"""

_APPLY_GAME_MOVE_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
if redis.call('HGET', KEYS[1], 'status') ~= 'playing' then
    return -1
end
local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '-1')
if version ~= tonumber(ARGV[1])
    or redis.call('HGET', KEYS[1], 'game_fen') ~= ARGV[2]
    or redis.call('HGET', KEYS[1], 'side_to_move') ~= ARGV[3] then
    return -2
end
local clock_field = 'red_time_ms'
local next_side = 'b'
local timeout_winner = 'b'
if ARGV[3] == 'b' then
    clock_field = 'black_time_ms'
    next_side = 'w'
    timeout_winner = 'w'
elseif ARGV[3] ~= 'w' then
    return -2
end
if ARGV[4] ~= next_side then
    return -2
end
local redis_time = redis.call('TIME')
local now_ms = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
local remaining_ms = tonumber(redis.call('HGET', KEYS[1], clock_field) or '0')
local turn_started_at_ms = tonumber(redis.call('HGET', KEYS[1], 'turn_started_at_ms') or now_ms)
remaining_ms = remaining_ms - math.max(0, now_ms - turn_started_at_ms)
if remaining_ms <= 0 then
    local next_version = version + 1
    redis.call('HSET', KEYS[1],
        clock_field, 0,
        'status', 'finished',
        'game_result', 'timeout',
        'game_winner', timeout_winner,
        'game_version', next_version)
    return -3
end
local next_version = version + 1
redis.call('HSET', KEYS[1],
    clock_field, remaining_ms,
    'game_fen', ARGV[5],
    'game_version', next_version,
    'side_to_move', next_side,
    'turn_started_at_ms', now_ms)
if ARGV[6] ~= '' then
    redis.call('HSET', KEYS[1],
        'status', 'finished',
        'game_result', ARGV[6],
        'game_winner', ARGV[7])
end
return 1
"""

_TIMEOUT_ROOM_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0
    or redis.call('HGET', KEYS[1], 'status') ~= 'playing' then
    return 0
end
local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '-1')
if version ~= tonumber(ARGV[1]) then
    return 0
end
local side = redis.call('HGET', KEYS[1], 'side_to_move')
local clock_field = 'red_time_ms'
local winner = 'b'
if side == 'b' then
    clock_field = 'black_time_ms'
    winner = 'w'
elseif side ~= 'w' then
    return 0
end
local redis_time = redis.call('TIME')
local now_ms = tonumber(redis_time[1]) * 1000 + math.floor(tonumber(redis_time[2]) / 1000)
local remaining_ms = tonumber(redis.call('HGET', KEYS[1], clock_field) or '0')
local turn_started_at_ms = tonumber(redis.call('HGET', KEYS[1], 'turn_started_at_ms') or now_ms)
remaining_ms = remaining_ms - math.max(0, now_ms - turn_started_at_ms)
if remaining_ms > 0 then
    return 0
end
redis.call('HSET', KEYS[1],
    clock_field, 0,
    'status', 'finished',
    'game_result', 'timeout',
    'game_winner', winner,
    'game_version', version + 1)
return 1
"""

_LEAVE_ROOM_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
local role = redis.call('HGET', KEYS[2], ARGV[1])
if not role then
    return -2
end
if role == 'player1' then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    redis.call('ZREM', KEYS[4], ARGV[2])
    return 2
end
local status = redis.call('HGET', KEYS[1], 'status')
if role == 'player2' and status == 'waiting' then
    redis.call('HSET', KEYS[1], 'player2_token', '')
    redis.call('HDEL', KEYS[2], ARGV[1])
    return 1
end
if role == 'player2' and status == 'playing' then
    redis.call('HSET', KEYS[1], 'player2_connected', 'false')
    return 3
end
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('SREM', KEYS[3], ARGV[1])
return 1
"""


def _room_key(room_id: int) -> str:
    return f"room:{room_id}"


def _participants_key(room_id: int) -> str:
    return f"room:{room_id}:participants"


def _spectators_key(room_id: int) -> str:
    return f"room:{room_id}:spectators"


def create_room(
    name: str,
    host_name: str = "Khách",
    timer_seconds: int = 30,
) -> tuple[dict[str, Any], str]:
    """Create a public waiting room and assign its creator to player slot one."""
    if timer_seconds not in {15, 30, 60}:
        raise ValueError("Room timer must be 15, 30, or 60 seconds")
    room_id = int(redis_client.incr(ROOM_SEQUENCE_KEY))
    host_token = secrets.token_urlsafe(32)
    invite_token = secrets.token_urlsafe(32)
    created_at = int(time.time())

    pipeline = redis_client.pipeline(transaction=True)
    pipeline.hset(
        _room_key(room_id),
        mapping={
            "id": room_id,
            "name": name,
            "host_name": host_name,
            "timer_seconds": timer_seconds,
            "visibility": "public",
            "status": "waiting",
            "host_token": host_token,
            "invite_token": invite_token,
            "player2_token": "",
            "player2_connected": "true",
            "created_at": created_at,
        },
    )
    pipeline.hset(_participants_key(room_id), host_token, "player1")
    pipeline.zadd(PUBLIC_ROOMS_KEY, {str(room_id): created_at})
    pipeline.execute()

    room = get_room(room_id)
    if room is None:
        raise RuntimeError("Room creation did not produce a readable room")
    return room, host_token


def get_or_create_invite_token(room_id: int) -> str | None:
    """Return the room's share token, adding one for rooms created by older code."""
    room_key = _room_key(room_id)
    if not redis_client.exists(room_key):
        return None

    invite_token = redis_client.hget(room_key, "invite_token")
    if invite_token:
        return str(invite_token)

    candidate = secrets.token_urlsafe(32)
    if redis_client.hsetnx(room_key, "invite_token", candidate):
        return candidate

    invite_token = redis_client.hget(room_key, "invite_token")
    return str(invite_token) if invite_token else None


def is_valid_invite_token(room_id: int, invite_token: str) -> bool:
    """Validate a room-level share token without exposing it in room summaries."""
    stored_token = get_or_create_invite_token(room_id)
    return bool(
        stored_token
        and secrets.compare_digest(stored_token, invite_token)
    )


def get_room(room_id: int) -> dict[str, Any] | None:
    """Return public room information without exposing participant tokens."""
    values = redis_client.hgetall(_room_key(room_id))
    if not values:
        return None

    player_count = 1 + int(bool(values.get("player2_token")))
    return {
        "id": int(values["id"]),
        "name": values["name"],
        "host_name": values.get("host_name", "Khách"),
        "timer_seconds": int(values.get("timer_seconds", 30)),
        "visibility": values["visibility"],
        "status": values["status"],
        "player_count": player_count,
        "spectator_count": int(redis_client.scard(_spectators_key(room_id))),
        "created_at": int(values["created_at"]),
    }


def list_public_rooms(limit: int = 100) -> list[dict[str, Any]]:
    """List public rooms that are still waiting for an opponent."""
    room_ids = redis_client.zrange(PUBLIC_ROOMS_KEY, 0, limit - 1)
    rooms: list[dict[str, Any]] = []
    for room_id_text in room_ids:
        room_id = int(room_id_text)
        room = get_room(room_id)
        if room is None or room["status"] != "waiting":
            redis_client.zrem(PUBLIC_ROOMS_KEY, room_id_text)
            continue
        rooms.append(room)
    return rooms


def join_room(room_id: int, participant_token: str) -> str | None:
    """Assign the next lobby joiner player two; later joins become spectators."""
    result = redis_client.eval(
        _JOIN_ROOM_SCRIPT,
        3,
        _room_key(room_id),
        _participants_key(room_id),
        _spectators_key(room_id),
        participant_token,
    )
    if result == -1:
        return None
    return str(result)


def get_participant_role(room_id: int, participant_token: str) -> str | None:
    """Return the role bound to a room access token."""
    role = redis_client.hget(_participants_key(room_id), participant_token)
    return str(role) if role else None


def start_room(room_id: int, host_token: str) -> int:
    """Start a room atomically and remove it from the public lobby."""
    return int(
        redis_client.eval(
            _START_ROOM_SCRIPT,
            2,
            _room_key(room_id),
            PUBLIC_ROOMS_KEY,
            host_token,
            room_id,
            STARTING_FEN,
        )
    )


def get_game_snapshot(room_id: int) -> dict[str, Any] | None:
    """Read board state and calculate live clocks using Redis server time."""
    values = redis_client.hgetall(_room_key(room_id))
    if not values or not values.get("game_fen"):
        return None

    redis_seconds, redis_microseconds = redis_client.time()
    server_time_ms = int(redis_seconds) * 1000 + int(redis_microseconds) // 1000
    side_to_move = values.get("side_to_move", "w")
    red_time_ms = int(values.get("red_time_ms", 0))
    black_time_ms = int(values.get("black_time_ms", 0))
    if values.get("status") == "playing":
        elapsed_ms = max(
            0,
            server_time_ms - int(values.get("turn_started_at_ms", server_time_ms)),
        )
        if side_to_move == "w":
            red_time_ms = max(0, red_time_ms - elapsed_ms)
        else:
            black_time_ms = max(0, black_time_ms - elapsed_ms)

    return {
        "room_id": room_id,
        "fen": values["game_fen"],
        "version": int(values.get("game_version", 0)),
        "side_to_move": side_to_move,
        "red_time_ms": red_time_ms,
        "black_time_ms": black_time_ms,
        "timer_seconds": int(values.get("timer_seconds", 30)),
        "status": values.get("status", "playing"),
        "result": values.get("game_result") or None,
        "winner": values.get("game_winner") or None,
        "server_time_ms": server_time_ms,
    }


def apply_game_move(
    room_id: int,
    expected_version: int,
    expected_fen: str,
    moving_side: str,
    next_side: str,
    next_fen: str,
    result: str | None = None,
    winner: str | None = None,
) -> int:
    """Atomically apply a validated move and charge its mover's clock.

    Returns 1 when applied, -1 when the game is no longer playing, -2 when
    another update won the race, and -3 when the mover timed out first.
    """
    if moving_side not in {"w", "b"} or next_side not in {"w", "b"}:
        raise ValueError("Move sides must be 'w' or 'b'")
    return int(
        redis_client.eval(
            _APPLY_GAME_MOVE_SCRIPT,
            1,
            _room_key(room_id),
            expected_version,
            expected_fen,
            moving_side,
            next_side,
            next_fen,
            result or "",
            winner or "",
        )
    )


def timeout_room(room_id: int, expected_version: int) -> bool:
    """Finish a room as a timeout if the active side's server clock expired."""
    return bool(
        redis_client.eval(
            _TIMEOUT_ROOM_SCRIPT,
            1,
            _room_key(room_id),
            expected_version,
        )
    )


def leave_room(room_id: int, participant_token: str) -> int:
    """Leave a room; the host leaving deletes that room permanently.

    Returns -1 if the room is missing, -2 for an unknown token, 1 for a leave,
    2 when the host deleted the room, and 3 when an active player disconnected
    while retaining their seat for reconnection.
    """
    return int(
        redis_client.eval(
            _LEAVE_ROOM_SCRIPT,
            4,
            _room_key(room_id),
            _participants_key(room_id),
            _spectators_key(room_id),
            PUBLIC_ROOMS_KEY,
            participant_token,
            room_id,
        )
    )
