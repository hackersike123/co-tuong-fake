"""Short-lived password-reset codes stored in Redis."""

import secrets

from .redis_connection import redis_client


OTP_TTL_SECONDS = 300
MAX_OTP_ATTEMPTS = 5

_VERIFY_OTP_SCRIPT = """
local code = redis.call('GET', KEYS[1])
if not code then
    redis.call('DEL', KEYS[2])
    return -1
end
if code == ARGV[1] then
    if ARGV[4] == 'consume' then
        redis.call('DEL', KEYS[1])
        redis.call('DEL', KEYS[2])
    end
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


def _password_reset_otp_key(email: str) -> str:
    return f"forgot_pwd:{email.strip().lower()}"


def _password_reset_attempts_key(email: str) -> str:
    return f"forgot_pwd_attempts:{email.strip().lower()}"


def _issue_otp(code_key: str, attempts_key: str) -> str:
    otp = f"{secrets.randbelow(1_000_000):06d}"
    pipeline = redis_client.pipeline(transaction=True)
    pipeline.set(code_key, otp, ex=OTP_TTL_SECONDS)
    pipeline.delete(attempts_key)
    pipeline.execute()
    return otp


def _check_otp(code_key: str, attempts_key: str, otp: str, *, consume: bool) -> int:
    result = redis_client.eval(
        _VERIFY_OTP_SCRIPT,
        2,
        code_key,
        attempts_key,
        otp,
        OTP_TTL_SECONDS,
        MAX_OTP_ATTEMPTS,
        "consume" if consume else "keep",
    )
    return int(result)


def issue_password_reset_otp(email: str) -> str:
    """Create a cryptographically random password-reset OTP with a 5-minute TTL."""
    return _issue_otp(
        _password_reset_otp_key(email),
        _password_reset_attempts_key(email),
    )


def consume_password_reset_otp(email: str, otp: str) -> int:
    """Check a reset code and atomically consume it if it matches."""
    return _check_otp(
        _password_reset_otp_key(email),
        _password_reset_attempts_key(email),
        otp,
        consume=True,
    )


def clear_password_reset_otp(email: str) -> None:
    """Remove the password-reset code and its attempt counter."""
    redis_client.delete(
        _password_reset_otp_key(email),
        _password_reset_attempts_key(email),
    )
