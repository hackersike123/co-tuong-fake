"""Password hashing helpers."""

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plaintext password with the recommended password algorithm."""
    return password_hash.hash(password)
