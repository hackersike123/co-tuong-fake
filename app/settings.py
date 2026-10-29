"""Environment-backed application settings."""

import os

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./co_tuong.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Co Tuong")
SMTP_USE_SSL = _env_bool("SMTP_USE_SSL", False)
SMTP_STARTTLS = _env_bool("SMTP_STARTTLS", True)
SMTP_TIMEOUT_SECONDS = float(os.getenv("SMTP_TIMEOUT_SECONDS", "10"))

JWT_SECRET = os.getenv("JWT_SECRET", "")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
