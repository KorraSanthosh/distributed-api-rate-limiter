import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from app.core.config import settings
from app.core.logging import logger
from app.repositories.redis_repository import RedisRepository
from app.services.analytics_service import AnalyticsService
from app.services.rate_limit_service import RateLimitService
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.analytics import AnalyticsMiddleware

# Import Route Modules
from app.api.v1.status import router as status_router
from app.api.v1.data import router as data_router
from app.api.v1.users import router as users_router
from app.api.v1.orders import router as orders_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manages application startup and shutdown lifecycle events."""
    logger.info("Starting up Distributed API Rate Limiter server...")

    # 1. Initialize repository singleton and attach to state
    redis_repo = RedisRepository()
    app.state.redis_repo = redis_repo

    # 2. Initialize domain service singletons and attach to state
    app.state.rate_limit_service = RateLimitService(redis_repo)
    app.state.analytics_service = AnalyticsService(redis_repo)

    # 3. Perform a startup ping check on Redis
    redis_alive = await redis_repo.ping()
    if not redis_alive:
        logger.critical(
            "CRITICAL: Failed to establish connection to Redis at startup. "
            "System will start in degraded mode (failing open)."
        )
    else:
        logger.info("Connected to Redis successfully.")

    yield  # API requests are served here

    # 4. Cleanup connection pools
    logger.info("Shutting down Distributed API Rate Limiter server...")
    await redis_repo.close()
    logger.info("Redis connections closed. Cleanup finished.")


# Initialize FastAPI instance
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# MIDDLEWARE REGISTRATION
# Note: FastAPI processes middlewares in LIFO (Last-In-First-Out) order.
#
# Execution Flow:
# 1. Incoming Request -> AnalyticsMiddleware -> RateLimiterMiddleware -> Router
# 2. Router Response -> RateLimiterMiddleware (adds limit headers) -> AnalyticsMiddleware (logs latency & status to Redis Stream) -> Client
#
# This ordering ensures that even if RateLimiterMiddleware blocks a request (429),
# the AnalyticsMiddleware still intercepts the 429 response and pushes it to Redis.
# ---------------------------------------------------------------------------
app.add_middleware(AnalyticsMiddleware)
app.add_middleware(RateLimiterMiddleware)

# Include API v1 Routers
app.include_router(status_router, prefix=settings.API_V1_STR, tags=["System Health"])
app.include_router(data_router, prefix=settings.API_V1_STR, tags=["Metrics Data"])
app.include_router(users_router, prefix=settings.API_V1_STR, tags=["Users Management"])
app.include_router(orders_router, prefix=settings.API_V1_STR, tags=["Orders Processing"])


@app.get(
    "/metrics",
    summary="Prometheus Metrics",
    description="Exposes application telemetry metrics for scraping.",
    tags=["System Monitoring"],
)
async def metrics() -> Response:
    """Generates the latest Prometheus metrics in text format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
