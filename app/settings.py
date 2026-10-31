"""Environment-backed application settings."""

import os
from urllib.parse import urlsplit

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./co_tuong.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:5173").rstrip("/")

_DEVELOPMENT_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8443",
    "http://127.0.0.1:8443",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://localhost:8002",
    "http://127.0.0.1:8002",
)


def _normalize_origin(value: str) -> str:
    origin = value.strip()
    parsed = urlsplit(origin)
    if (
        origin == "*"
        or parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or "*" in parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"Invalid CORS origin: {value!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid CORS origin: {value!r}") from exc
    host = parsed.hostname
    if host is None:
        raise ValueError(f"Invalid CORS origin: {value!r}")
    host = f"[{host.lower()}]" if ":" in host else host.lower()
    default_port = 80 if parsed.scheme.lower() == "http" else 443
    netloc = host if port is None or port == default_port else f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{netloc}"


def _cors_allowed_origins() -> tuple[str, ...]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS")
    values = _DEVELOPMENT_ORIGINS if configured is None else configured.split(",")
    origins = tuple(dict.fromkeys(_normalize_origin(value) for value in values if value.strip()))
    if configured and not origins:
        raise ValueError("CORS_ALLOWED_ORIGINS must contain at least one origin")
    return origins


CORS_ALLOWED_ORIGINS = _cors_allowed_origins()

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
