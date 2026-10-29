"""Password hashing helpers."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from .settings import ACCESS_TOKEN_MINUTES, JWT_SECRET


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password with the recommended password algorithm."""
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Compare a plaintext password with its stored hash."""
    try:
        return password_hash.verify(password, hashed_password)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, email: str, username: str | None) -> tuple[str, int]:
    """Create a signed access JWT with a configured 15–30 minute lifetime."""
    if len(JWT_SECRET) < 32 or JWT_SECRET.startswith("replace-with-a-random-secret"):
        raise RuntimeError("JWT_SECRET must contain at least 32 characters")
    if not 15 <= ACCESS_TOKEN_MINUTES <= 30:
        raise RuntimeError("ACCESS_TOKEN_MINUTES must be between 15 and 30")

    now = datetime.now(timezone.utc)
    expires_in = ACCESS_TOKEN_MINUTES * 60
    token = jwt.encode(
        {
            "sub": str(user_id),
            "email": email,
            "username": username,
            "iat": now,
            "exp": now + timedelta(seconds=expires_in),
            "jti": str(uuid4()),
            "token_type": "access",
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    return token, expires_in


def create_refresh_token() -> str:
    """Create an opaque, high-entropy browser refresh token."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Hash opaque tokens before persisting them in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
