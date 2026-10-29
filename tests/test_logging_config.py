"""Tests for JSON log formatting and structured socket context."""

import json
import logging

from app.logging_config import JsonFormatter


def test_json_formatter_includes_structured_socket_fields() -> None:
    record = logging.LogRecord(
        name="app.routers.rooms",
        level=logging.WARNING,
        pathname="rooms.py",
        lineno=10,
        msg="WebSocket authentication failed",
        args=(),
        exc_info=None,
    )
    record.event = "websocket.auth_failed"
    record.room_id = 42
    record.reason = "unknown_room_or_participant"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["level"] == "WARNING"
    assert payload["message"] == "WebSocket authentication failed"
    assert payload["event"] == "websocket.auth_failed"
    assert payload["room_id"] == 42
    assert payload["reason"] == "unknown_room_or_participant"
