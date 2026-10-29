"""Redis-backed storage and atomic lifecycle operations for public rooms."""

import secrets
import time
from typing import Any

from redis import Redis

from .settings import REDIS_URL


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
redis.call('HSET', KEYS[1], 'status', 'playing')
redis.call('ZREM', KEYS[2], ARGV[2])
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


def create_room(name: str) -> tuple[dict[str, Any], str]:
    """Create a public waiting room and assign its creator to player slot one."""
    room_id = int(redis_client.incr(ROOM_SEQUENCE_KEY))
    host_token = secrets.token_urlsafe(32)
    created_at = int(time.time())

    pipeline = redis_client.pipeline(transaction=True)
    pipeline.hset(
        _room_key(room_id),
        mapping={
            "id": room_id,
            "name": name,
            "visibility": "public",
            "status": "waiting",
            "host_token": host_token,
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


def get_room(room_id: int) -> dict[str, Any] | None:
    """Return public room information without exposing participant tokens."""
    values = redis_client.hgetall(_room_key(room_id))
    if not values:
        return None

    player_count = 1 + int(bool(values.get("player2_token")))
    return {
        "id": int(values["id"]),
        "name": values["name"],
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
