"""Shared synchronous Redis client used by room and OTP services."""

from redis import Redis

from .settings import REDIS_URL


redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=5,
)
