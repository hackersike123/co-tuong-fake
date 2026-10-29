"""Structured JSON logging for the API and Uvicorn."""

import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Any


_CONTEXT_FIELDS = (
    "event",
    "worker_id",
    "room_id",
    "role",
    "reason",
    "outcome",
    "scope",
    "status_code",
    "request_id",
)


class JsonFormatter(logging.Formatter):
    """Format standard and application log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Configure application and Uvicorn logs to use the JSON formatter."""
    normalized_level = level.upper()
    if not isinstance(logging.getLevelName(normalized_level), int):
        normalized_level = "INFO"
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                    "stream": "ext://sys.stdout",
                }
            },
            "loggers": {
                "app": {
                    "handlers": ["console"],
                    "level": normalized_level,
                    "propagate": False,
                },
                "uvicorn": {
                    "handlers": ["console"],
                    "level": normalized_level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console"],
                    "level": normalized_level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console"],
                    "level": normalized_level,
                    "propagate": False,
                },
            },
            "root": {"handlers": ["console"], "level": normalized_level},
        }
    )
