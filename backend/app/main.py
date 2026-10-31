"""Nexus Agentic AI Assistant - FastAPI Application Entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.api import api_router
from app.core.config import settings
from app.database.session import check_db_connection, init_db
from app.services.scheduler import scheduler_background_loop

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nexus.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle management."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}...")
    # Initialize DB tables
    try:
        await init_db()
        logger.info("Database schemas initialized.")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")

    # Start background scheduler loop
    scheduler_task = asyncio.create_task(scheduler_background_loop(poll_interval_seconds=10))

    yield

    scheduler_task.cancel()
    logger.info("Nexus backend shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Agentic AI Productivity Assistant with Voice, LangGraph, and Windows Companion Agent",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

from app.core.rate_limiter import RateLimitMiddleware, SlidingWindowRateLimiter

# In-memory rate limiter: 150 req/min default
rate_limiter = SlidingWindowRateLimiter(default_limit=150, window_seconds=60)
app.add_middleware(RateLimitMiddleware, limiter=rate_limiter)

# Configure CORS
origins = settings.BACKEND_CORS_ORIGINS
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if isinstance(origins, list) else [origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root level /health endpoint (required by Phase 1 spec)
@app.get("/health", tags=["system"], summary="System root health check")
async def root_health() -> Dict[str, Any]:
    """Root health check endpoint."""
    db_status = await check_db_connection()
    return {
        "status": "healthy" if db_status.get("status") == "connected" else "degraded",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": db_status,
    }


# Include API v1 router
app.include_router(api_router, prefix=settings.API_V1_STR)

# Mount Static Showcase Website
import os
from fastapi.staticfiles import StaticFiles

root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
website_dir = os.path.join(root_dir, "website")
if os.path.exists(website_dir):
    app.mount("/website", StaticFiles(directory=website_dir, html=True), name="website")
    app.mount("/landing", StaticFiles(directory=website_dir, html=True), name="landing")

# Direct root WebSocket route for voice streaming matching /ws/voice/{session_id}
from app.api.v1.endpoints.voice import voice_websocket_channel
from app.api.v1.endpoints.desktop import companion_websocket_endpoint
import uuid

@app.websocket("/ws/voice/{session_id}")
async def direct_voice_websocket(websocket: WebSocket, session_id: uuid.UUID):
    """Direct root voice streaming channel."""
    await voice_websocket_channel(websocket, session_id)


@app.websocket("/ws/desktop/companion")
async def direct_companion_websocket(websocket: WebSocket):
    """Direct root WebSocket for Windows desktop companion."""
    await companion_websocket_endpoint(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

