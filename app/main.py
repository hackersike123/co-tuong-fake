"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from .database import Base, engine
from .routers.auth import router as auth_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Create development tables when the application starts."""
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Co Tuong API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["accounts"])


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Report that the API process is running."""
    return {"status": "ok"}
