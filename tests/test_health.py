"""Tests for dependency health reporting."""

import json
import time

import fakeredis
import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from app import main, room_store


def test_health_reports_database_redis_and_websocket_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(main, "engine", test_engine)
    monkeypatch.setattr(room_store, "redis_client", fakeredis.FakeRedis())
    monkeypatch.setattr(
        main.room_hub,
        "health_status",
        lambda: {
            "status": "ok",
            "redis_pubsub": "ready",
            "active_connections": 2,
            "worker_id": "test-worker",
        },
    )

    response = main.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload["status"] == "ok"
    assert payload["checks"]["database"]["status"] == "ok"
    assert payload["checks"]["redis"]["status"] == "ok"
    assert payload["checks"]["websocket"]["active_connections"] == 2
    test_engine.dispose()


def test_health_returns_service_unavailable_when_dependencies_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableDatabase:
        def connect(self) -> None:
            raise SQLAlchemyError("database unavailable")

    class UnavailableRedis:
        def ping(self) -> None:
            raise RedisError("redis unavailable")

    monkeypatch.setattr(main, "engine", UnavailableDatabase())
    monkeypatch.setattr(room_store, "redis_client", UnavailableRedis())
    monkeypatch.setattr(
        main.room_hub,
        "health_status",
        lambda: {
            "status": "unavailable",
            "redis_pubsub": "unavailable",
            "active_connections": 0,
            "worker_id": "test-worker",
        },
    )

    response = main.health_check()
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "degraded"
    assert payload["checks"]["database"]["status"] == "unavailable"
    assert payload["checks"]["redis"]["status"] == "unavailable"
    assert payload["checks"]["websocket"]["status"] == "unavailable"


def test_health_http_route_reports_live_runtime_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    try:
        room_store.redis_client.ping()
    except RedisError:
        pytest.skip("Configured Redis server is unavailable")

    test_engine = create_engine("sqlite:///:memory:")
    monkeypatch.setattr(main, "engine", test_engine)
    with TestClient(main.app) as client:
        deadline = time.monotonic() + 3
        while main.room_hub.health_status()["status"] != "ok":
            if time.monotonic() >= deadline:
                raise AssertionError("WebSocket Redis Pub/Sub did not become ready")
            time.sleep(0.01)

        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["checks"]["database"]["status"] == "ok"
    assert response.json()["checks"]["redis"]["status"] == "ok"
    assert response.json()["checks"]["websocket"]["redis_pubsub"] == "ready"
    test_engine.dispose()
