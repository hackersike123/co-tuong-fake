"""ASGI middleware for validating browser WebSocket origins."""

import logging
from collections.abc import Iterable
from typing import Any


logger = logging.getLogger(__name__)


class WebSocketOriginMiddleware:
    """Reject WebSocket handshakes whose Origin is not explicitly allowed."""

    def __init__(self, app: Any, allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        origin_headers = [
            value.decode("latin-1")
            for name, value in scope.get("headers", ())
            if name.lower() == b"origin"
        ]
        origin = origin_headers[0] if len(origin_headers) == 1 else None
        if origin not in self.allowed_origins:
            logger.warning(
                "Rejected WebSocket handshake with an untrusted origin",
                extra={
                    "event": "websocket.origin_rejected",
                    "path": scope.get("path", ""),
                    "origin": origin,
                },
            )
            await send(
                {
                    "type": "websocket.close",
                    "code": 1008,
                    "reason": "Origin is not allowed",
                }
            )
            return

        await self.app(scope, receive, send)
