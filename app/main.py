"""FastAPI application entry point."""

from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .database import Base, engine, upgrade_sqlite_schema
from .logging_config import configure_logging
from .room_hub import room_hub
from . import room_store
from .routers.auth import router as auth_router
from .routers.pve import router as pve_router
from .routers.rooms import router as rooms_router
from .routers.ws_api import router as websocket_api_router
from .settings import LOG_LEVEL


configure_logging(LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Initialize dependencies and the cross-worker room event subscriber."""
    try:
        Base.metadata.create_all(bind=engine)
        upgrade_sqlite_schema()
    except SQLAlchemyError:
        logger.exception(
            "Database schema initialization failed",
            extra={"event": "database.initialization_failed"},
        )

    await room_hub.start()
    try:
        yield
    finally:
        await room_hub.close()


app = FastAPI(title="Co Tuong API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["accounts"])
app.include_router(rooms_router, prefix="/api/v1/rooms", tags=["rooms"])
app.include_router(pve_router, prefix="/api/v1/pve", tags=["single-player"])
app.include_router(websocket_api_router, prefix="/api/v1", tags=["websocket-rpc"])


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
