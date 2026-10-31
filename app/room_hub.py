"""WebSocket fan-out and Redis Pub/Sub relay for lobby and room events."""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError
from starlette.concurrency import run_in_threadpool

from .match_service import record_completed_match
from .room_store import (
    acquire_room_timer_lease,
    delete_room,
    finalize_reconnect_forfeit,
    get_game_snapshot,
    timeout_room,
)
from .settings import REDIS_URL


logger = logging.getLogger(__name__)
ROOM_EVENTS_CHANNEL = "co_tuong:websocket:events"


class RoomHub:
    """Track connected clients and broadcast room lifecycle events."""

    def __init__(self) -> None:
        self._lobby_clients: set[WebSocket] = set()
        self._room_clients: dict[int, set[WebSocket]] = defaultdict(set)
        self._active_connection_count = 0
        self._room_participant_tokens: dict[WebSocket, str] = {}
        self._outbound_queues: dict[WebSocket, asyncio.Queue[dict[str, Any]]] = {}
        self._sender_tasks: dict[WebSocket, asyncio.Task[None]] = {}
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}
        self._timer_tasks: dict[int, asyncio.Task[None]] = {}
        self._reconnect_tasks: dict[tuple[int, str], asyncio.Task[None]] = {}
        self._event_bus_redis: AsyncRedis | None = None
        self._subscriber_task: asyncio.Task[None] | None = None
        self._worker_id = uuid4().hex
        self._pubsub_ready = False
        self._publish_failed = False
        self._closing = False
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the Redis Pub/Sub listener used to fan events across workers."""
        if self._subscriber_task is not None and not self._subscriber_task.done():
            return
        self._closing = False
        if self._event_bus_redis is None:
            self._event_bus_redis = AsyncRedis.from_url(
                REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
            )
        await self._event_bus_redis.ping()
        self._subscriber_task = asyncio.create_task(
            self._subscribe_to_room_events(),
            name=f"room-event-subscriber-{self._worker_id}",
        )
        logger.info(
            "Room event subscriber started",
            extra={"event": "websocket.pubsub_starting", "worker_id": self._worker_id},
        )

    async def close(self) -> None:
        """Stop managed background tasks and close the Pub/Sub Redis pool."""
        self._closing = True
        tasks = [
            *self._timer_tasks.values(),
            *self._reconnect_tasks.values(),
            *self._sender_tasks.values(),
        ]
        task = self._subscriber_task
        self._subscriber_task = None
        if task is not None:
            tasks.append(task)

        self._timer_tasks.clear()
        self._reconnect_tasks.clear()
        self._sender_tasks.clear()
        self._outbound_queues.clear()
        self._send_locks.clear()
        for background_task in tasks:
            if background_task is not asyncio.current_task():
                background_task.cancel()
        pending = [background_task for background_task in tasks if background_task is not asyncio.current_task()]
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        async with self._lock:
            self._lobby_clients.clear()
            self._room_clients.clear()
            self._room_participant_tokens.clear()
            self._active_connection_count = 0

        self._pubsub_ready = False
        self._publish_failed = False
        client = self._event_bus_redis
        self._event_bus_redis = None
        if client is not None:
            await client.aclose()

    def health_status(self) -> dict[str, str | int]:
        """Report the local WebSocket hub and its cross-worker event channel."""
        ready = self._pubsub_ready and not self._publish_failed
        return {
            "status": "ok" if ready else "unavailable",
            "redis_pubsub": "ready" if ready else "unavailable",
            "active_connections": self._active_connection_count,
            "worker_id": self._worker_id,
        }

    async def _subscribe_to_room_events(self) -> None:
        """Reconnect the subscriber after transient Redis failures."""
        while not self._closing:
            client = self._event_bus_redis
            if client is None:
                return
            try:
                async with client.pubsub() as pubsub:
                    await pubsub.subscribe(ROOM_EVENTS_CHANNEL)
                    self._pubsub_ready = True
                    self._publish_failed = False
                    logger.info(
                        "Room event subscriber ready",
                        extra={"event": "websocket.pubsub_ready", "worker_id": self._worker_id},
                    )
                    async for message in pubsub.listen():
                        if self._closing:
                            break
                        if message.get("type") != "message":
                            continue
                        await self._handle_cluster_message(message.get("data"))
            except asyncio.CancelledError:
                raise
            except (RedisError, OSError):
                logger.exception(
                    "Room event subscriber lost its Redis connection",
                    extra={
                        "event": "websocket.pubsub_disconnected",
                        "worker_id": self._worker_id,
                    },
                )
            finally:
                self._pubsub_ready = False
            if not self._closing:
                await asyncio.sleep(1)

    async def _handle_cluster_message(self, raw_message: Any) -> None:
        """Decode a published event and enqueue it for this worker's sockets."""
        try:
            envelope = json.loads(raw_message)
        except (TypeError, json.JSONDecodeError):
            logger.warning(
                "Ignoring malformed room event from Redis",
                extra={"event": "websocket.pubsub_invalid_message", "worker_id": self._worker_id},
            )
            return
        if not isinstance(envelope, dict) or envelope.get("origin_worker") == self._worker_id:
            return
        event = envelope.get("event")
        if not isinstance(event, dict):
            return
        if envelope.get("scope") == "lobby":
            self._deliver_lobby_event(event)
        elif envelope.get("scope") == "room":
            room_id = envelope.get("room_id")
            if isinstance(room_id, int):
                await self._deliver_room_event(room_id, event)

    async def _publish_cluster_event(
        self,
        scope: str,
        event: dict[str, Any],
        room_id: int | None = None,
    ) -> None:
        """Publish an event across workers, then deliver it to local sockets."""
        client = self._event_bus_redis
        if client is not None:
            envelope = {
                "origin_worker": self._worker_id,
                "scope": scope,
                "room_id": room_id,
                "event": event,
            }
            try:
                await client.publish(
                    ROOM_EVENTS_CHANNEL,
                    json.dumps(envelope, ensure_ascii=False, separators=(",", ":")),
                )
                self._publish_failed = False
            except (RedisError, OSError):
                self._publish_failed = True
                logger.exception(
                    "Could not publish room event across workers",
                    extra={
                        "event": "websocket.pubsub_publish_failed",
                        "worker_id": self._worker_id,
                        "room_id": room_id,
                        "scope": scope,
                    },
                )

        if scope == "lobby":
            self._deliver_lobby_event(event)
        elif room_id is not None:
            await self._deliver_room_event(room_id, event)

    def _deliver_lobby_event(self, event: dict[str, Any]) -> None:
        self._enqueue_events(tuple(self._lobby_clients), event)

    async def _deliver_room_event(self, room_id: int, event: dict[str, Any]) -> None:
        if event.get("type") == "room.access_revoked":
            participant_token = event.get("participant_token")
            if isinstance(participant_token, str):
                await self._revoke_local_participant(room_id, participant_token)
            return
        self._enqueue_events(tuple(self._room_clients.get(room_id, ())), event)

    async def _revoke_local_participant(
        self,
        room_id: int,
        participant_token: str,
    ) -> None:
        """Drop a revoked participant's local sockets before more room events."""
        revoked_sockets: list[WebSocket] = []
        async with self._lock:
            clients = self._room_clients.get(room_id)
            if clients is None:
                return
            for websocket in tuple(clients):
                if self._room_participant_tokens.get(websocket) != participant_token:
                    continue
                clients.discard(websocket)
                self._room_participant_tokens.pop(websocket, None)
                self._active_connection_count -= 1
                queue = self._outbound_queues.get(websocket)
                if queue is not None:
                    while not queue.empty():
                        try:
                            queue.get_nowait()
                            queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                self._remove_sender(websocket)
                revoked_sockets.append(websocket)
            if not clients:
                self._room_clients.pop(room_id, None)

        for websocket in revoked_sockets:
            try:
                await websocket.close(code=4403, reason="Room access was revoked")
            except (RuntimeError, WebSocketDisconnect):
                pass

    async def revoke_participant(
        self,
        room_id: int,
        participant_token: str,
        *,
        drain: bool = False,
    ) -> None:
        """Revoke sockets across workers after the participant leaves a room."""
        if drain:
            async with self._lock:
                queues = tuple(
                    self._outbound_queues[websocket]
                    for websocket in self._room_clients.get(room_id, ())
                    if self._room_participant_tokens.get(websocket) == participant_token
                    and websocket in self._outbound_queues
                )
            for queue in queues:
                try:
                    await asyncio.wait_for(queue.join(), timeout=1)
                except TimeoutError:
                    logger.warning(
                        "Could not flush final room event before revoking participant socket",
                        extra={"event": "websocket.revoke_flush_timeout", "room_id": room_id},
                    )
        await self._publish_cluster_event(
            "room",
            {"type": "room.access_revoked", "participant_token": participant_token},
            room_id,
        )

    def _enqueue_events(self, clients: tuple[WebSocket, ...], event: dict[str, Any]) -> None:
        for websocket in clients:
            queue = self._outbound_queues.get(websocket)
            if queue is None:
                continue
            # Coalesce timer ticks when a client is slow so lifecycle events
            # remain ordered and do not get stuck behind stale clock updates.
            if event.get("type") == "timer_tick" and queue.qsize() > 0:
                continue
            queue.put_nowait(event)

    async def connect_lobby(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if websocket not in self._lobby_clients:
                self._lobby_clients.add(websocket)
                self._active_connection_count += 1
            self._prepare_sender(websocket)

    async def disconnect_lobby(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._lobby_clients:
                self._lobby_clients.discard(websocket)
                self._active_connection_count -= 1
            self._remove_sender(websocket)

    async def connect_room(
        self,
        room_id: int,
        websocket: WebSocket,
        participant_token: str,
    ) -> None:
        await websocket.accept()
        async with self._lock:
            clients = self._room_clients[room_id]
            if websocket not in clients:
                clients.add(websocket)
                self._active_connection_count += 1
            self._room_participant_tokens[websocket] = participant_token
            self._prepare_sender(websocket)

    async def disconnect_room(self, room_id: int, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._room_clients.get(room_id)
            if clients is None:
                return
            if websocket in clients:
                clients.discard(websocket)
                self._active_connection_count -= 1
            if not clients:
                self._room_clients.pop(room_id, None)
            self._room_participant_tokens.pop(websocket, None)
            self._remove_sender(websocket)

    async def has_participant_connection(
        self,
        room_id: int,
        participant_token: str,
    ) -> bool:
        """Check whether another local socket still represents this participant."""
        async with self._lock:
            return any(
                websocket in self._room_clients.get(room_id, ())
                and token == participant_token
                for websocket, token in self._room_participant_tokens.items()
            )

    def _prepare_sender(self, websocket: WebSocket) -> None:
        self._outbound_queues[websocket] = asyncio.Queue()
        self._send_locks[websocket] = asyncio.Lock()

    def _remove_sender(self, websocket: WebSocket) -> None:
        self._outbound_queues.pop(websocket, None)
        self._send_locks.pop(websocket, None)
        task = self._sender_tasks.pop(websocket, None)
        if task is not None and task is not asyncio.current_task():
            task.cancel()

    async def start_sender(self, websocket: WebSocket) -> None:
        """Start queued event delivery after the socket's initial snapshot."""
        async with self._lock:
            queue = self._outbound_queues.get(websocket)
            task = self._sender_tasks.get(websocket)
            if queue is None or (task is not None and not task.done()):
                return
            self._sender_tasks[websocket] = asyncio.create_task(
                self._send_loop(websocket, queue),
                name="room-websocket-sender",
            )

    async def send_to_client(self, websocket: WebSocket, event: dict[str, Any]) -> None:
        """Serialize direct replies with queued broadcasts for this socket."""
        lock = self._send_locks.get(websocket)
        if lock is None:
            await websocket.send_json(event)
            return
        async with lock:
            await websocket.send_json(event)

    async def broadcast_lobby(self, event: dict[str, Any]) -> None:
        await self._publish_cluster_event("lobby", event)

    async def broadcast_room(self, room_id: int, event: dict[str, Any]) -> None:
        await self._publish_cluster_event("room", event, room_id)

    async def ensure_timer(self, room_id: int) -> None:
        """Start one server-side timer loop for an active room."""
        try:
            snapshot = await run_in_threadpool(get_game_snapshot, room_id)
        except RedisError:
            logger.exception("Could not start timer for room %s", room_id)
            return
        if snapshot is None or snapshot["status"] != "playing":
            return

        await self._restore_reconnect_timeouts(room_id, snapshot)
        task = self._timer_tasks.get(room_id)
        if task is not None and not task.done():
            return
        self._timer_tasks[room_id] = asyncio.create_task(
            self._timer_loop(room_id),
            name=f"room-timer-{room_id}",
        )

    async def stop_timer(self, room_id: int) -> None:
        """Cancel the local per-room clock broadcaster."""
        task = self._timer_tasks.pop(room_id, None)
        if task is None or task is asyncio.current_task():
            return
        task.cancel()

    async def stop_reconnect_timeout(self, room_id: int, role: str) -> None:
        """Cancel the reconnect deadline after that player returns or leaves."""
        task = self._reconnect_tasks.pop((room_id, role), None)
        if task is None or task is asyncio.current_task():
            return
        task.cancel()

    async def stop_room_timers(self, room_id: int) -> None:
        """Stop game and reconnect timers for a room that is closing or finished."""
        await self.stop_timer(room_id)
        for task_room_id, role in tuple(self._reconnect_tasks):
            if task_room_id == room_id:
                await self.stop_reconnect_timeout(room_id, role)

    async def schedule_reconnect_timeout(
        self,
        room_id: int,
        role: str,
        deadline_ms: int,
        delay_ms: int,
    ) -> None:
        """Schedule the server's 60-second grace period for a disconnected player."""
        await self.stop_reconnect_timeout(room_id, role)
        self._reconnect_tasks[(room_id, role)] = asyncio.create_task(
            self._reconnect_timeout_loop(room_id, role, deadline_ms, delay_ms),
            name=f"room-reconnect-{room_id}-{role}",
        )

    async def _restore_reconnect_timeouts(
        self,
        room_id: int,
        snapshot: dict[str, Any],
    ) -> None:
        """Recreate local deadlines from Redis after a worker starts or reconnects."""
        for role, deadline_ms in snapshot.get("reconnect_deadlines_ms", {}).items():
            key = (room_id, role)
            task = self._reconnect_tasks.get(key)
            if task is not None and not task.done():
                continue
            delay_ms = max(0, int(deadline_ms) - snapshot["server_time_ms"])
            self._reconnect_tasks[key] = asyncio.create_task(
                self._reconnect_timeout_loop(room_id, role, int(deadline_ms), delay_ms),
                name=f"room-reconnect-{room_id}-{role}",
            )

    async def publish_forfeit(
        self,
        room_id: int,
        event: dict[str, Any],
        participant_token: str | None = None,
    ) -> None:
        """Stop all clocks and tell the room that a player forfeited."""
        await self.stop_room_timers(room_id)
        await self.broadcast_room(room_id, event)
        if participant_token is not None:
            await self.revoke_participant(room_id, participant_token, drain=True)

    async def close_after_forfeit(
        self,
        room_id: int,
        event: dict[str, Any],
        participant_token: str | None = None,
    ) -> None:
        """Broadcast a host's loss before deleting the room and closing its clients."""
        await self.stop_room_timers(room_id)
        await self.broadcast_room(room_id, event)
        try:
            deleted = await run_in_threadpool(delete_room, room_id)
        except RedisError:
            logger.exception("Could not delete forfeited room %s", room_id)
            return
        if deleted:
            await self.broadcast_lobby(
                {"type": "room.removed", "room_id": room_id, "reason": "host_forfeit"}
            )
            await self.broadcast_room(
                room_id,
                {"type": "room.closed", "room_id": room_id, "reason": "host_forfeit"},
            )
            if participant_token is not None:
                await self.revoke_participant(room_id, participant_token, drain=True)

    async def _reconnect_timeout_loop(
        self,
        room_id: int,
        role: str,
        deadline_ms: int,
        delay_ms: int,
    ) -> None:
        current_task = asyncio.current_task()
        try:
            await asyncio.sleep(max(0, delay_ms) / 1000)
            while True:
                try:
                    result = await run_in_threadpool(
                        finalize_reconnect_forfeit,
                        room_id,
                        role,
                        deadline_ms,
                    )
                except RedisError:
                    logger.exception(
                        "Could not finalize reconnect deadline for room %s (%s)",
                        room_id,
                        role,
                    )
                    await asyncio.sleep(1)
                    continue

                if result == -1:
                    # The local worker clock can wake slightly before Redis time.
                    await asyncio.sleep(0.25)
                    continue
                if result == 1:
                    try:
                        game = await run_in_threadpool(get_game_snapshot, room_id)
                    except RedisError:
                        logger.exception("Could not read forfeited game %s", room_id)
                        return
                    await self.stop_room_timers(room_id)
                    if game is not None:
                        await run_in_threadpool(record_completed_match, room_id)
                        await self.broadcast_room(
                            room_id,
                            {
                                "type": "game.forfeit",
                                "room_id": room_id,
                                "reason": "reconnect_timeout",
                                "loser_role": role,
                                "game": game,
                            },
                        )
                return
        finally:
            key = (room_id, role)
            if self._reconnect_tasks.get(key) is current_task:
                self._reconnect_tasks.pop(key, None)

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
                await self._restore_reconnect_timeouts(room_id, snapshot)
                if snapshot["paused"]:
                    continue

                try:
                    owns_timer = await run_in_threadpool(
                        acquire_room_timer_lease,
                        room_id,
                        self._worker_id,
                    )
                except RedisError:
                    logger.exception("Could not acquire timer lease for room %s", room_id)
                    continue
                if not owns_timer:
                    continue

                try:
                    snapshot = await run_in_threadpool(get_game_snapshot, room_id)
                except RedisError:
                    logger.exception("Could not refresh timer snapshot for room %s", room_id)
                    continue
                if snapshot is None or snapshot["status"] != "playing" or snapshot["paused"]:
                    continue

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
                        await run_in_threadpool(record_completed_match, room_id)
                        await self.broadcast_room(
                            room_id,
                            {
                                "type": "game.timeout",
                                "room_id": room_id,
                                "game": final_snapshot,
                            },
                        )
                        await self.broadcast_room(
                            room_id,
                            {
                                "type": "game_over",
                                "room_id": room_id,
                                "result": final_snapshot.get("result"),
                                "reason": final_snapshot.get("reason") or "timeout",
                                "winner": final_snapshot.get("winner"),
                                "notation": final_snapshot.get("notation", ""),
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
                        "paused": snapshot["paused"],
                        "server_time_ms": snapshot["server_time_ms"],
                    },
                )
        finally:
            if self._timer_tasks.get(room_id) is current_task:
                self._timer_tasks.pop(room_id, None)

    async def _send_loop(
        self,
        websocket: WebSocket,
        queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        while True:
            event = await queue.get()
            try:
                await self.send_to_client(websocket, event)
            except (RuntimeError, WebSocketDisconnect):
                logger.debug("WebSocket send failed; waiting for disconnect cleanup")
                return
            finally:
                queue.task_done()


room_hub = RoomHub()
