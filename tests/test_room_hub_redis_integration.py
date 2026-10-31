"""Integration tests for room event fan-out through Redis Pub/Sub."""

import asyncio

import pytest
from redis.exceptions import RedisError

from app.room_hub import RoomHub
from app.room_store import redis_client


class RecordingWebSocket:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.received = asyncio.Event()
        self.closed = asyncio.Event()
        self.close_code: int | None = None

    async def accept(self) -> None:
        return None

    async def send_json(self, event: dict[str, object]) -> None:
        self.events.append(event)
        self.received.set()

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.close_code = code
        self.closed.set()


def test_room_and_lobby_events_reach_another_worker() -> None:
    try:
        redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    async def exercise_pubsub() -> None:
        publisher = RoomHub()
        subscriber = RoomHub()
        room_socket = RecordingWebSocket()
        lobby_socket = RecordingWebSocket()
        await publisher.start()
        await subscriber.start()
        try:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + 3
            while (
                publisher.health_status()["redis_pubsub"] != "ready"
                or subscriber.health_status()["redis_pubsub"] != "ready"
            ):
                if loop.time() >= deadline:
                    raise AssertionError("Redis Pub/Sub workers did not become ready")
                await asyncio.sleep(0.01)

            await subscriber.connect_room(9_876_543, room_socket, "test-participant")
            await subscriber.start_sender(room_socket)
            await subscriber.connect_lobby(lobby_socket)
            await subscriber.start_sender(lobby_socket)

            move_event: dict[str, object] = {
                "type": "move_made",
                "room_id": 9_876_543,
                "version": 7,
            }
            lobby_event: dict[str, object] = {
                "type": "room.removed",
                "room_id": 9_876_543,
            }
            await publisher.broadcast_room(9_876_543, move_event)
            await publisher.broadcast_lobby(lobby_event)
            await asyncio.wait_for(
                asyncio.gather(room_socket.received.wait(), lobby_socket.received.wait()),
                timeout=3,
            )

            assert move_event in room_socket.events
            assert lobby_event in lobby_socket.events

            await publisher.revoke_participant(9_876_543, "test-participant")
            await asyncio.wait_for(room_socket.closed.wait(), timeout=3)
            assert room_socket.close_code == 4403
        finally:
            await subscriber.disconnect_room(9_876_543, room_socket)
            await subscriber.disconnect_lobby(lobby_socket)
            await publisher.close()
            await subscriber.close()

    asyncio.run(exercise_pubsub())
