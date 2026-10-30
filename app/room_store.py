"""Redis-backed storage and atomic lifecycle operations for public rooms."""

import secrets
import time
from typing import Any
from uuid import uuid4

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
RECONNECT_TIMEOUT_MS = 60_000
ROOM_TIMER_LEASE_MS = 3_000

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
if redis.call('HGET', KEYS[1], 'allow_spectators') == 'false' then
    return -2
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
    'player1_connected', 'true',
    'player2_connected', 'true',
    'game_paused', 'false',
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
if redis.call('HGET', KEYS[1], 'status') ~= 'playing'
    or redis.call('HGET', KEYS[1], 'game_paused') == 'true' then
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
    or redis.call('HGET', KEYS[1], 'status') ~= 'playing'
    or redis.call('HGET', KEYS[1], 'game_paused') == 'true' then
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
local status = redis.call('HGET', KEYS[1], 'status')
if role == 'player1' and status == 'playing' then
    local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '0')
    redis.call('HSET', KEYS[1],
        'status', 'finished',
        'game_result', 'forfeit',
        'game_winner', 'b',
        'game_paused', 'true',
        'game_version', version + 1)
    return 4
end
if role == 'player1' then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    redis.call('ZREM', KEYS[4], ARGV[2])
    return 2
end
if role == 'player2' and status == 'waiting' then
    redis.call('HSET', KEYS[1], 'player2_token', '')
    redis.call('HSET', KEYS[1], 'player2_connected', 'false')
    redis.call('HDEL', KEYS[2], ARGV[1])
    return 1
end
if role == 'player2' and status == 'playing' then
    local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '0')
    redis.call('HSET', KEYS[1], 'player2_connected', 'false')
    redis.call('HSET', KEYS[1],
        'status', 'finished',
        'game_result', 'forfeit',
        'game_winner', 'w',
        'game_paused', 'true',
        'game_version', version + 1,
        'player2_token', '')
    redis.call('HDEL', KEYS[2], ARGV[1])
    return 5
end
if role == 'player2' then
    redis.call('HSET', KEYS[1], 'player2_token', '', 'player2_connected', 'false')
end
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('SREM', KEYS[3], ARGV[1])
return 1
"""

_MARK_PLAYER_DISCONNECTED_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return {-1, '', 0, 0}
end
local role = redis.call('HGET', KEYS[2], ARGV[1])
if not role then
    return {-2, '', 0, 0}
end
local status = redis.call('HGET', KEYS[1], 'status')
if role == 'player1' and status == 'waiting' then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    redis.call('ZREM', KEYS[4], ARGV[2])
    return {2, role, 0, 0}
end
if role == 'player1' and status == 'finished' then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
    redis.call('ZREM', KEYS[4], ARGV[2])
    return {2, role, 0, 0}
end
if role == 'player2' and status == 'waiting' then
    redis.call('HSET', KEYS[1], 'player2_token', '', 'player2_connected', 'false')
    redis.call('HDEL', KEYS[2], ARGV[1])
    return {1, role, 0, 0}
end
if role == 'player1' or role == 'player2' then
    if status ~= 'playing' then
        if role == 'player2' then
            redis.call('HSET', KEYS[1], 'player2_token', '', 'player2_connected', 'false')
        end
        redis.call('HDEL', KEYS[2], ARGV[1])
        return {1, role, 0, 0}
    end
    local connected_field = role .. '_connected'
    local deadline_field = role .. '_reconnect_deadline_ms'
    local existing_deadline = tonumber(redis.call('HGET', KEYS[1], deadline_field) or '0')
    if redis.call('HGET', KEYS[1], connected_field) == 'false' and existing_deadline > 0 then
        local now = redis.call('TIME')
        local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
        return {3, role, existing_deadline, now_ms}
    end
    local now = redis.call('TIME')
    local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
    if redis.call('HGET', KEYS[1], 'game_paused') ~= 'true' then
        local side = redis.call('HGET', KEYS[1], 'side_to_move')
        local clock_field = 'red_time_ms'
        local timeout_winner = 'b'
        if side == 'b' then
            clock_field = 'black_time_ms'
            timeout_winner = 'w'
        elseif side ~= 'w' then
            return {0, role, 0, now_ms}
        end
        local remaining = tonumber(redis.call('HGET', KEYS[1], clock_field) or '0')
        local turn_started = tonumber(redis.call('HGET', KEYS[1], 'turn_started_at_ms') or now_ms)
        remaining = remaining - math.max(0, now_ms - turn_started)
        if remaining <= 0 then
            local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '0')
            redis.call('HSET', KEYS[1], clock_field, 0)
            redis.call('HSET', KEYS[1], connected_field, 'false')
            redis.call('HSET', KEYS[1],
                'status', 'finished',
                'game_result', 'timeout',
                'game_winner', timeout_winner,
                'game_paused', 'true',
                'game_version', version + 1)
            return {4, role, 0, now_ms}
        end
        redis.call('HSET', KEYS[1], clock_field, remaining)
    end
    local deadline_ms = now_ms + tonumber(ARGV[3])
    redis.call('HSET', KEYS[1],
        connected_field, 'false',
        deadline_field, deadline_ms,
        'game_paused', 'true',
        'turn_started_at_ms', now_ms)
    return {3, role, deadline_ms, now_ms}
end
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('SREM', KEYS[3], ARGV[1])
return {1, role, 0, 0}
"""

_MARK_PLAYER_RECONNECTED_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then
    return -1
end
if redis.call('HGET', KEYS[2], ARGV[1]) ~= ARGV[2] then
    return -2
end
if ARGV[2] ~= 'player1' and ARGV[2] ~= 'player2' then
    return 0
end
local status = redis.call('HGET', KEYS[1], 'status')
local connected_field = ARGV[2] .. '_connected'
local deadline_field = ARGV[2] .. '_reconnect_deadline_ms'
if status == 'finished'
    and redis.call('HGET', KEYS[1], 'game_result') == 'forfeit'
    and redis.call('HGET', KEYS[1], connected_field) == 'false' then
    return -4
end
if status == 'playing' and redis.call('HGET', KEYS[1], connected_field) == 'false' then
    local deadline_ms = tonumber(redis.call('HGET', KEYS[1], deadline_field) or '0')
    local now = redis.call('TIME')
    local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
    if deadline_ms > 0 and now_ms >= deadline_ms then
        local winner = 'b'
        if ARGV[2] == 'player2' then winner = 'w' end
        local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '0')
        redis.call('HSET', KEYS[1],
            'status', 'finished',
            'game_result', 'forfeit',
            'game_winner', winner,
            'game_paused', 'true',
            'game_version', version + 1)
        redis.call('HDEL', KEYS[1], 'player1_reconnect_deadline_ms', 'player2_reconnect_deadline_ms')
        return -3
    end
    redis.call('HSET', KEYS[1], connected_field, 'true')
    redis.call('HDEL', KEYS[1], deadline_field)
    local other_role = 'player1'
    if ARGV[2] == 'player1' then other_role = 'player2' end
    if redis.call('HGET', KEYS[1], other_role .. '_connected') ~= 'false' then
        redis.call('HSET', KEYS[1], 'game_paused', 'false', 'turn_started_at_ms', now_ms)
    end
    return 1
end
if status == 'waiting' then
    redis.call('HSET', KEYS[1], connected_field, 'true')
end
return 0
"""

_FINALIZE_RECONNECT_FORFEIT_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0
    or redis.call('HGET', KEYS[1], 'status') ~= 'playing' then
    return 0
end
local role = ARGV[1]
if role ~= 'player1' and role ~= 'player2' then return 0 end
local connected_field = role .. '_connected'
local deadline_field = role .. '_reconnect_deadline_ms'
if redis.call('HGET', KEYS[1], connected_field) ~= 'false'
    or redis.call('HGET', KEYS[1], deadline_field) ~= ARGV[2] then
    return 0
end
local now = redis.call('TIME')
local now_ms = tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000)
if now_ms < tonumber(ARGV[2]) then return -1 end
local winner = 'b'
if role == 'player2' then winner = 'w' end
local version = tonumber(redis.call('HGET', KEYS[1], 'game_version') or '0')
redis.call('HSET', KEYS[1],
    'status', 'finished',
    'game_result', 'forfeit',
    'game_winner', winner,
    'game_paused', 'true',
    'game_version', version + 1)
redis.call('HDEL', KEYS[1], 'player1_reconnect_deadline_ms', 'player2_reconnect_deadline_ms')
return 1
"""

_DELETE_ROOM_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0 then return 0 end
redis.call('DEL', KEYS[1], KEYS[2], KEYS[3])
redis.call('ZREM', KEYS[4], ARGV[1])
return 1
"""

_ACQUIRE_ROOM_TIMER_LEASE_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 0
    or redis.call('HGET', KEYS[1], 'status') ~= 'playing'
    or redis.call('HGET', KEYS[1], 'game_paused') == 'true' then
    return -1
end
local owner = redis.call('GET', KEYS[2])
if not owner or owner == ARGV[1] then
    redis.call('SET', KEYS[2], ARGV[1], 'PX', ARGV[2])
    return 1
end
return 0
"""

_RELEASE_ROOM_TIMER_LEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""


def _room_key(room_id: int) -> str:
    return f"room:{room_id}"


def _participants_key(room_id: int) -> str:
    return f"room:{room_id}:participants"


def _spectators_key(room_id: int) -> str:
    return f"room:{room_id}:spectators"


def _timer_lease_key(room_id: int) -> str:
    return f"{_room_key(room_id)}:timer-owner"


def create_room(
    name: str,
    host_name: str = "Khách",
    timer_seconds: int = 30,
    *,
    is_public: bool = True,
    password_hash: str | None = None,
    allow_spectators: bool = True,
) -> tuple[dict[str, Any], str]:
    """Create a waiting room and assign its creator to player slot one."""
    if timer_seconds not in {15, 30, 60}:
        raise ValueError("Room timer must be 15, 30, or 60 seconds")
    room_id = int(redis_client.incr(ROOM_SEQUENCE_KEY))
    room_uuid = uuid4().hex
    host_token = secrets.token_urlsafe(32)
    invite_token = secrets.token_urlsafe(32)
    created_at = int(time.time())

    pipeline = redis_client.pipeline(transaction=True)
    pipeline.hset(
        _room_key(room_id),
        mapping={
            "id": room_id,
            "room_uuid": room_uuid,
            "name": name,
            "room_name": name,
            "host_name": host_name,
            "timer_seconds": timer_seconds,
            "time_per_move": timer_seconds,
            "visibility": "public" if is_public else "private",
            "is_public": "true" if is_public else "false",
            "password_hash": password_hash or "",
            "allow_spectators": "true" if allow_spectators else "false",
            "status": "waiting",
            "host_token": host_token,
            "invite_token": invite_token,
            "player2_token": "",
            "player2_connected": "true",
            "created_at": created_at,
        },
    )
    pipeline.hset(_participants_key(room_id), host_token, "player1")
    if is_public:
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

    room_uuid = values.get("room_uuid")
    if not room_uuid:
        candidate = uuid4().hex
        redis_client.hsetnx(_room_key(room_id), "room_uuid", candidate)
        room_uuid = redis_client.hget(_room_key(room_id), "room_uuid") or candidate
    stored_is_public = values.get("is_public")
    is_public = (
        stored_is_public != "false"
        if stored_is_public is not None
        else values.get("visibility", "public") == "public"
    )
    timer_seconds = int(values.get("time_per_move", values.get("timer_seconds", 30)))
    player_count = 1 + int(bool(values.get("player2_token")))
    return {
        "id": int(values["id"]),
        "room_id": int(values["id"]),
        "room_uuid": str(room_uuid),
        "room_name": values.get("room_name", values["name"]),
        "name": values["name"],
        "host_name": values.get("host_name", "Khách"),
        "timer_seconds": timer_seconds,
        "time_per_move": timer_seconds,
        "visibility": "public" if is_public else "private",
        "is_public": is_public,
        "has_password": bool(values.get("password_hash")),
        "allow_spectators": values.get("allow_spectators", "true") != "false",
        "status": values["status"],
        "player_count": player_count,
        "spectator_count": int(redis_client.scard(_spectators_key(room_id))),
        "created_at": int(values["created_at"]),
    }


def get_room_password_hash(room_id: int) -> str | None:
    """Return a stored room password hash without exposing it in room summaries."""
    password_hash = redis_client.hget(_room_key(room_id), "password_hash")
    return str(password_hash) if password_hash else None


def list_public_rooms(limit: int = 100) -> list[dict[str, Any]]:
    """List public rooms that are still waiting for an opponent."""
    room_ids = redis_client.zrange(PUBLIC_ROOMS_KEY, 0, limit - 1)
    rooms: list[dict[str, Any]] = []
    for room_id_text in room_ids:
        room_id = int(room_id_text)
        room = get_room(room_id)
        if room is None or not room["is_public"] or room["status"] != "waiting":
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
    if result == -2:
        return "spectators_disabled"
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
    paused = values.get("game_paused") == "true"
    if values.get("status") == "playing" and not paused:
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
        "paused": paused,
        "disconnected_players": [
            role
            for role in ("player1", "player2")
            if values.get(f"{role}_connected") == "false"
        ],
        "reconnect_deadlines_ms": {
            role: int(values[f"{role}_reconnect_deadline_ms"])
            for role in ("player1", "player2")
            if values.get(f"{role}_reconnect_deadline_ms")
        },
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
    """Handle an intentional leave and forfeit active player games immediately.

    Returns -1 if the room is missing, -2 for an unknown token, 1 for a leave,
    2 when the host deleted the room, 4 when the host forfeited an active game,
    and 5 when player two forfeited an active game.
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


def mark_player_disconnected(room_id: int, participant_token: str) -> dict[str, Any]:
    """Mark a socket drop and start a Redis-timed 60-second reconnect window."""
    result = redis_client.eval(
        _MARK_PLAYER_DISCONNECTED_SCRIPT,
        4,
        _room_key(room_id),
        _participants_key(room_id),
        _spectators_key(room_id),
        PUBLIC_ROOMS_KEY,
        participant_token,
        room_id,
        RECONNECT_TIMEOUT_MS,
    )
    code, role, deadline_ms, now_ms = result
    return {
        "code": int(code),
        "role": str(role),
        "deadline_ms": int(deadline_ms),
        "delay_ms": max(0, int(deadline_ms) - int(now_ms)),
    }


def mark_player_reconnected(room_id: int, role: str, participant_token: str) -> int:
    """Restore a player's seat unless their Redis-backed grace period expired.

    Returns 1 when the player reconnects during the grace period, 0 when no
    reconnect was pending, -1 when the room is missing, -2 for an invalid role
    or token, -3 when the deadline expired and the player was just forfeited,
    and -4 when they already forfeited and are reconnecting too late.
    """
    if role not in {"player1", "player2"}:
        return -2
    return int(
        redis_client.eval(
            _MARK_PLAYER_RECONNECTED_SCRIPT,
            2,
            _room_key(room_id),
            _participants_key(room_id),
            participant_token,
            role,
        )
    )


def finalize_reconnect_forfeit(room_id: int, role: str, deadline_ms: int) -> int:
    """Forfeit a disconnected player if the matching Redis deadline expired.

    Returns 1 when the forfeit was applied, 0 when the player reconnected or
    the game ended, and -1 when the server-side deadline has not arrived yet.
    """
    if role not in {"player1", "player2"}:
        return 0
    return int(
        redis_client.eval(
            _FINALIZE_RECONNECT_FORFEIT_SCRIPT,
            1,
            _room_key(room_id),
            role,
            deadline_ms,
        )
    )


def delete_room(room_id: int) -> bool:
    """Delete a room after its final event has been delivered to connected clients."""
    return bool(
        redis_client.eval(
            _DELETE_ROOM_SCRIPT,
            4,
            _room_key(room_id),
            _participants_key(room_id),
            _spectators_key(room_id),
            PUBLIC_ROOMS_KEY,
            room_id,
        )
    )


def acquire_room_timer_lease(room_id: int, worker_id: str) -> bool:
    """Acquire or renew the single-worker lease for a room's timer broadcaster."""
    result = redis_client.eval(
        _ACQUIRE_ROOM_TIMER_LEASE_SCRIPT,
        2,
        _room_key(room_id),
        _timer_lease_key(room_id),
        worker_id,
        ROOM_TIMER_LEASE_MS,
    )
    return result == 1


def release_room_timer_lease(room_id: int, worker_id: str) -> bool:
    """Release a timer lease only when the current worker owns it."""
    return bool(
        redis_client.eval(
            _RELEASE_ROOM_TIMER_LEASE_SCRIPT,
            1,
            _timer_lease_key(room_id),
            worker_id,
        )
    )
