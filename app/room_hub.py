"""In-process WebSocket fan-out for the public lobby and room events."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from .room_store import get_game_snapshot, timeout_room


logger = logging.getLogger(__name__)


class RoomHub:
    """Track connected clients and broadcast room lifecycle events."""

    def __init__(self) -> None:
        self._lobby_clients: set[WebSocket] = set()
        self._room_clients: dict[int, set[WebSocket]] = defaultdict(set)
        self._timer_tasks: dict[int, asyncio.Task[None]] = {}
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

    async def ensure_timer(self, room_id: int) -> None:
        """Start one server-side timer loop for an active room."""
        try:
            snapshot = await run_in_threadpool(get_game_snapshot, room_id)
        except RedisError:
            logger.exception("Could not start timer for room %s", room_id)
            return
        if snapshot is None or snapshot["status"] != "playing":
            return

        task = self._timer_tasks.get(room_id)
        if task is not None and not task.done():
            return
        self._timer_tasks[room_id] = asyncio.create_task(
            self._timer_loop(room_id),
            name=f"room-timer-{room_id}",
        )

    async def stop_timer(self, room_id: int) -> None:
        """Cancel an active room's timer task after the room is deleted."""
        task = self._timer_tasks.pop(room_id, None)
        if task is None or task is asyncio.current_task():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _timer_loop(self, room_id: int) -> None:
        current_task = asyncio.current_task()
        try:
            while True:
                await asyncio.sleep(1)
                try:
                    snapshot = await run_in_threadpool(get_game_snapshot, room_id)
                except RedisError:
                    logger.exception("Could not read timer for room %s", room_id)
                    continue

                if snapshot is None or snapshot["status"] != "playing":
                    return

                active_clock = (
                    snapshot["red_time_ms"]
                    if snapshot["side_to_move"] == "w"
                    else snapshot["black_time_ms"]
                )
                if active_clock <= 0:
                    try:
                        timed_out = await run_in_threadpool(
                            timeout_room,
                            room_id,
                            snapshot["version"],
                        )
                        final_snapshot = await run_in_threadpool(
                            get_game_snapshot,
                            room_id,
                        )
                    except RedisError:
                        logger.exception("Could not apply timeout for room %s", room_id)
                        continue

                    if timed_out and final_snapshot is not None:
                        await self.broadcast_room(
                            room_id,
                            {
                                "type": "game.timeout",
                                "room_id": room_id,
                                "game": final_snapshot,
                            },
                        )
                    if final_snapshot is None or final_snapshot["status"] != "playing":
                        return
                    continue

                await self.broadcast_room(
                    room_id,
                    {
                        "type": "timer_tick",
                        "room_id": room_id,
                        "version": snapshot["version"],
                        "side_to_move": snapshot["side_to_move"],
                        "red_time_ms": snapshot["red_time_ms"],
                        "black_time_ms": snapshot["black_time_ms"],
                        "server_time_ms": snapshot["server_time_ms"],
                    },
                )
        finally:
            if self._timer_tasks.get(room_id) is current_task:
                self._timer_tasks.pop(room_id, None)

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
