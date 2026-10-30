"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from . import otp_store
from .database import Base, engine, upgrade_sqlite_schema
from .logging_config import configure_logging
from .origin import WebSocketOriginMiddleware
from .room_hub import room_hub
from . import room_store
from .routers.auth import router as auth_router
from .routers.pve import router as pve_router
from .routers.rooms import router as rooms_router
from .settings import CORS_ALLOWED_ORIGINS, LOG_LEVEL


configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize shared database/Redis resources and release them on shutdown."""
    logger.info("Starting FastAPI application", extra={"event": "app.starting"})
    try:
        Base.metadata.create_all(bind=engine)
        upgrade_sqlite_schema()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        logger.info("Database connection ready", extra={"event": "database.ready"})

        room_store.redis_client.ping()
        logger.info("Redis connection ready", extra={"event": "redis.ready"})

        await room_hub.start()
    except Exception:
        logger.exception(
            "FastAPI application startup failed",
            extra={"event": "app.startup_failed"},
        )
        await _close_application_resources()
        raise

    logger.info("FastAPI application started", extra={"event": "app.started"})
    try:
        yield
    finally:
        await _close_application_resources()


async def _close_application_resources() -> None:
    """Close each shared resource even if another cleanup step fails."""
    logger.info("Stopping FastAPI application", extra={"event": "app.stopping"})
    try:
        await room_hub.close()
    except Exception:
        logger.exception(
            "Could not stop room background tasks",
            extra={"event": "websocket.shutdown_failed"},
        )

    sync_redis_clients = (room_store.redis_client, otp_store.redis_client)
    closed_client_ids: set[int] = set()
    for client in sync_redis_clients:
        if id(client) in closed_client_ids:
            continue
        closed_client_ids.add(id(client))
        try:
            client.close()
        except Exception:
            logger.exception(
                "Could not close Redis connection pool",
                extra={"event": "redis.shutdown_failed"},
            )

    try:
        engine.dispose()
    except Exception:
        logger.exception(
            "Could not dispose database connection pool",
            extra={"event": "database.shutdown_failed"},
        )
    logger.info("FastAPI application stopped", extra={"event": "app.stopped"})


app = FastAPI(title="Co Tuong API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    WebSocketOriginMiddleware,
    allowed_origins=CORS_ALLOWED_ORIGINS,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ALLOWED_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["accounts"])
app.include_router(rooms_router, prefix="/api/v1/rooms", tags=["rooms"])
app.include_router(pve_router, prefix="/api/v1/pve", tags=["single-player"])


@app.get("/demo/rooms", include_in_schema=False)
def room_lobby_demo() -> FileResponse:
    """Serve the lightweight room-creation modal for local demonstrations."""
    demo_path = Path(__file__).parent / "static" / "room_lobby.html"
    return FileResponse(demo_path, media_type="text/html; charset=utf-8")


@app.get("/health", tags=["health"], include_in_schema=False)
@app.get("/api/health", tags=["health"])
def health_check() -> JSONResponse:
    """Check the database, Redis, and cross-worker WebSocket event bus."""
    checks: dict[str, dict[str, str | int]] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except SQLAlchemyError:
        logger.warning(
            "Database health check failed",
            exc_info=True,
            extra={"event": "health.check_failed", "reason": "database"},
        )
        checks["database"] = {"status": "unavailable"}

    try:
        room_store.redis_client.ping()
        checks["redis"] = {"status": "ok"}
    except RedisError:
        logger.warning(
            "Redis health check failed",
            exc_info=True,
            extra={"event": "health.check_failed", "reason": "redis"},
        )
        checks["redis"] = {"status": "unavailable"}

    checks["websocket"] = room_hub.health_status()
    healthy = all(check.get("status") == "ok" for check in checks.values())
    response = {"status": "ok" if healthy else "degraded", "checks": checks}
    return JSONResponse(
        content=response,
        status_code=200 if healthy else 503,
    )
