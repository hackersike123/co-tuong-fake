"""In-process WebSocket fan-out for the public lobby and room events."""

import asyncio
from collections.abc import Awaitable, Callable
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect


class RoomHub:
    """Track connected clients and broadcast room lifecycle events."""

    def __init__(self) -> None:
        self._lobby_clients: set[WebSocket] = set()
        self._room_clients: dict[int, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect_lobby(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._lobby_clients.add(websocket)

    async def disconnect_lobby(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._lobby_clients.discard(websocket)

    async def connect_room(self, room_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._room_clients[room_id].add(websocket)

    async def disconnect_room(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._room_clients.get(room_id)
            if clients is None:
                return
            clients.discard(websocket)
            if not clients:
                self._room_clients.pop(room_id, None)

    async def broadcast_lobby(self, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = tuple(self._lobby_clients)
        await self._broadcast(clients, event, self.disconnect_lobby)

    async def broadcast_room(self, room_id: int, event: dict[str, Any]) -> None:
        async with self._lock:
            clients = tuple(self._room_clients.get(room_id, ()))
        await self._broadcast(
            clients,
            event,
            lambda websocket: self.disconnect_room(room_id, websocket),
        )

    async def _broadcast(
        self,
        clients: tuple[WebSocket, ...],
        event: dict[str, Any],
        disconnect: Callable[[WebSocket], Awaitable[None]],
    ) -> None:
        stale_clients: list[WebSocket] = []
        for websocket in clients:
            try:
                await websocket.send_json(event)
            except (RuntimeError, WebSocketDisconnect):
                stale_clients.append(websocket)

        for websocket in stale_clients:
            await disconnect(websocket)


room_hub = RoomHub()
