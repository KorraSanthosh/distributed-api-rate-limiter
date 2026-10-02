import time
import asyncio
import logging
from typing import Callable, Awaitable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.schemas.analytics import RequestAnalyticsLog
from app.services.analytics_service import AnalyticsService

logger = logging.getLogger("app")


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Asynchronously logs request properties to Redis Streams for real-time visualization."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.perf_counter()

        # Execute downstream middlewares & routes
        response = await call_next(request)

        # Calculate final request processing latency
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Paths bypassed from telemetry dashboard ingestion to prevent noise
        bypass_paths = [
            "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
            "/api/v1/analytics",  # dashboard polling: neither rate limited nor logged as traffic
        ]
        endpoint = request.url.path

        if any(endpoint.startswith(path) for path in bypass_paths):
            return response

        # Read context injected by upstream RateLimiterMiddleware
        request_id = getattr(request.state, "request_id", "unknown")
        client_ip = getattr(request.state, "client_ip", "127.0.0.1")
        method = request.method
        status_code = response.status_code

        # If status code is 429, request was blocked
        allowed = status_code != 429

        # Instantiate log schema
        log_event = RequestAnalyticsLog(
            request_id=request_id,
            timestamp=time.time(),
            client_ip=client_ip,
            method=method,
            endpoint=endpoint,
            status_code=status_code,
            latency_ms=round(latency_ms, 2),
            allowed=allowed,
        )

        # Fire-and-forget logging to avoid delaying the client response
        analytics_service: AnalyticsService = request.app.state.analytics_service
        asyncio.create_task(self._safely_persist_event(analytics_service, log_event))

        return response

    async def _safely_persist_event(
        self, service: AnalyticsService, log_event: RequestAnalyticsLog
    ) -> None:
        """Safely saves log events to Redis without throwing uncaught exceptions to worker threads."""
        try:
            await service.log_request(log_event)
        except Exception as e:
            logger.error(f"Failed to record analytics event in background task: {e}")
