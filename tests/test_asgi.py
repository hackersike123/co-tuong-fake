"""ASGI, origin policy, and application lifespan regression tests."""

import asyncio
import logging

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

from app import main, otp_store, room_store
from app.logging_config import UvicornAccessQueryFilter
from app.settings import CORS_ALLOWED_ORIGINS, _normalize_origin


def test_main_exposes_rest_and_websocket_routes_from_one_fastapi_app() -> None:
    assert isinstance(main.app, FastAPI)
    route_paths = {
        route.path for route in main.app.routes if hasattr(route, "path")
    }
    room_websocket_paths = {
        route.path
        for route in main.rooms_router.routes
        if isinstance(route, WebSocketRoute)
    }
    pve_websocket_paths = {
        route.path
        for route in main.pve_router.routes
        if isinstance(route, WebSocketRoute)
    }

    assert "/api/health" in route_paths
    assert "/ws" in room_websocket_paths
    assert "/{room_id}/ws" in room_websocket_paths
    assert "/ws" in pve_websocket_paths
    assert room_store.redis_client is otp_store.redis_client


def test_rest_endpoint_and_cors_preflight_allow_a_configured_origin() -> None:
    origin = CORS_ALLOWED_ORIGINS[0]
    client = TestClient(main.app)

    response = client.get("/openapi.json", headers={"Origin": origin})
    preflight = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin


def test_rest_cors_does_not_grant_an_unconfigured_origin() -> None:
    response = TestClient(main.app).get(
        "/openapi.json",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["*", "https://*.example.com"])
def test_origin_configuration_rejects_wildcards(origin: str) -> None:
    with pytest.raises(ValueError, match="Invalid CORS origin"):
        _normalize_origin(origin)


def test_uvicorn_access_logs_redact_websocket_query_tokens() -> None:
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1234",
            "GET",
            "/api/v1/rooms/7/ws?participant_token=secret-token",
            "1.1",
            101,
        ),
        exc_info=None,
    )

    assert UvicornAccessQueryFilter().filter(record)
    assert "secret-token" not in record.getMessage()
    assert "/api/v1/rooms/7/ws HTTP/1.1" in record.getMessage()


def test_untrusted_websocket_origin_is_rejected_before_route_authentication() -> None:
    client = TestClient(main.app)

    with pytest.raises(WebSocketDisconnect) as rejected:
        with client.websocket_connect(
            "/api/v1/rooms/ws",
            headers={"Origin": "https://untrusted.example"},
        ):
            pytest.fail("The WebSocket route should not accept an untrusted origin")

    assert rejected.value.code == 1008


def test_valid_websocket_origin_connects_with_existing_participant_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(room_store, "redis_client", fake_redis)
    room, participant_token = room_store.create_room("Origin validation", "Host", 30)
    client = TestClient(main.app)

    with client.websocket_connect(
        f"/api/v1/rooms/{room['id']}/ws?participant_token={participant_token}",
        headers={"Origin": CORS_ALLOWED_ORIGINS[0]},
    ) as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "room.snapshot"
        assert snapshot["role"] == "player1"


class _FakeConnection:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def __enter__(self) -> "_FakeConnection":
        self.events.append("database.connect")
        return self

    def __exit__(self, *_args: object) -> None:
        self.events.append("database.disconnect")

    def execute(self, _statement: object) -> None:
        self.events.append("database.ping")


class _FakeEngine:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self.events)

    def dispose(self) -> None:
        self.events.append("database.dispose")


class _FakeRedis:
    def __init__(self, events: list[str], *, fail_ping: bool = False) -> None:
        self.events = events
        self.fail_ping = fail_ping
        self.close_calls = 0

    def ping(self) -> bool:
        self.events.append("redis.ping")
        if self.fail_ping:
            raise RedisError("redis unavailable")
        return True

    def close(self) -> None:
        self.close_calls += 1
        self.events.append("redis.close")


def _prepare_fake_lifespan_resources(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    fail_startup: bool = False,
) -> _FakeRedis:
    fake_redis = _FakeRedis(events)
    fake_engine = _FakeEngine(events)

    def create_all(*, bind: object) -> None:
        assert bind is fake_engine
        events.append("database.schema")

    async def start_room_hub() -> None:
        events.append("websocket.start")
        if fail_startup:
            raise RedisError("pubsub unavailable")

    async def close_room_hub() -> None:
        events.append("websocket.close")

    monkeypatch.setattr(main, "engine", fake_engine)
    monkeypatch.setattr(main.Base.metadata, "create_all", create_all)
    monkeypatch.setattr(main, "upgrade_sqlite_schema", lambda: events.append("database.upgrade"))
    monkeypatch.setattr(room_store, "redis_client", fake_redis)
    monkeypatch.setattr(otp_store, "redis_client", fake_redis)
    monkeypatch.setattr(main.room_hub, "start", start_room_hub)
    monkeypatch.setattr(main.room_hub, "close", close_room_hub)
    return fake_redis


def test_lifespan_initializes_shared_resources_and_closes_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    fake_redis = _prepare_fake_lifespan_resources(monkeypatch, events)

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            events.append("application.ready")

    asyncio.run(exercise_lifespan())

    assert events.index("database.ping") < events.index("redis.ping")
    assert events.index("redis.ping") < events.index("websocket.start")
    assert events.index("websocket.close") < events.index("redis.close")
    assert events.index("redis.close") < events.index("database.dispose")
    assert fake_redis.close_calls == 1


def test_lifespan_startup_failure_closes_resources_already_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    fake_redis = _prepare_fake_lifespan_resources(
        monkeypatch,
        events,
        fail_startup=True,
    )

    async def exercise_lifespan() -> None:
        async with main.lifespan(main.app):
            pytest.fail("Startup failure must prevent the application from serving")

    with pytest.raises(RedisError, match="pubsub unavailable"):
        asyncio.run(exercise_lifespan())

    assert "websocket.close" in events
    assert "redis.close" in events
    assert "database.dispose" in events
    assert fake_redis.close_calls == 1
