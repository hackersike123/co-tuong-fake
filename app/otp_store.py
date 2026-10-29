"""Short-lived email verification codes stored in Redis."""

import secrets

from redis import Redis

from .settings import REDIS_URL


OTP_TTL_SECONDS = 300
MAX_OTP_ATTEMPTS = 5

redis_client = Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=3,
    socket_timeout=5,
)

_VERIFY_OTP_SCRIPT = """
local code = redis.call('GET', KEYS[1])
if not code then
    redis.call('DEL', KEYS[2])
    return -1
end
if code == ARGV[1] then
    return 1
end
local attempts = redis.call('INCR', KEYS[2])
if attempts == 1 then
    redis.call('EXPIRE', KEYS[2], ARGV[2])
end
if attempts >= tonumber(ARGV[3]) then
    redis.call('DEL', KEYS[1])
    redis.call('DEL', KEYS[2])
    return -2
end
return 0
"""


def _otp_key(user_id: int) -> str:
    return f"email-otp:{user_id}"


def _attempts_key(user_id: int) -> str:
    return f"email-otp-attempts:{user_id}"


def _issue_otp(code_key: str, attempts_key: str) -> str:
    otp = f"{secrets.randbelow(1_000_000):06d}"
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(code_key, otp, ex=OTP_TTL_SECONDS)
    pipeline.delete(attempts_key)
    pipeline.execute()
    return otp


def _check_otp(code_key: str, attempts_key: str, otp: str) -> int:
    result = redis_client.eval(
        _VERIFY_OTP_SCRIPT,
        2,
        code_key,
        attempts_key,
        otp,
        OTP_TTL_SECONDS,
        MAX_OTP_ATTEMPTS,
    )
    return int(result)


def issue_email_otp(user_id: int) -> str:
    """Create a cryptographically random 6-digit OTP with a 5-minute TTL."""
    return _issue_otp(_otp_key(user_id), _attempts_key(user_id))


def verify_email_otp(user_id: int, otp: str) -> int:
    """Atomically compare a code and count wrong attempts.

    Returns 1 for a match, 0 for a wrong code, -1 for an expired code, and
    -2 after the maximum number of incorrect attempts.
    """
    return _check_otp(_otp_key(user_id), _attempts_key(user_id), otp)


def clear_email_otp(user_id: int) -> None:
    """Remove the code and its attempt counter after registration completes."""
    redis_client.delete(_otp_key(user_id), _attempts_key(user_id))
