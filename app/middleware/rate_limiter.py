import time
import uuid
import logging
from typing import Callable, Awaitable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUESTS_BLOCKED_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    APP_ERRORS_TOTAL,
)
from app.schemas.rate_limit import RateLimitErrorResponse, RateLimitErrorDetail
from app.services.rate_limit_service import RateLimitService

logger = logging.getLogger("app")


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to enforce rate limits and collect request-level latency."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 1. Initialize Trace Context and Timings
        start_time = time.perf_counter()
        
        # Inject or extract Request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Extract Client IP correctly (considering proxy headers)
        client_ip = self._extract_client_ip(request)
        request.state.client_ip = client_ip

        # Path bypass list (avoid rate limiting docs, metrics, and static assets)
        bypass_paths = ["/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico"]
        endpoint = request.url.path
        method = request.method

        if any(endpoint.startswith(path) for path in bypass_paths):
            # Skip rate limiting check for bypassed endpoints
            response = await call_next(request)
            # Record metrics for bypassed paths
            latency = (time.perf_counter() - start_time) * 1000
            HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(latency / 1000.0)
            return response

        # 2. Perform Rate Limiting check
        rate_limit_service: RateLimitService = request.app.state.rate_limit_service
        timestamp = time.time()
        
        allowed = True
        current_count = 0
        limit = 0
        burst_limit = 0
        reset_time = timestamp

        try:
            # Check limits via service
            result = await rate_limit_service.evaluate_request(
                client_ip=client_ip,
                endpoint=endpoint,
                method=method,
                timestamp=timestamp,
            )
            allowed = result.allowed
            current_count = result.current_count
            limit = result.limit
            burst_limit = result.burst_limit
            reset_time = result.reset_time

        except Exception as e:
            # Fail-Open Logic: If Redis/Services are down, log error and allow requests through
            APP_ERRORS_TOTAL.labels(exception_type=type(e).__name__, endpoint=endpoint).inc()
            logger.error(
                f"RateLimiterMiddleware database outage. Falling open. Error: {e}",
                extra={"request_id": request_id, "client_ip": client_ip, "endpoint": endpoint},
            )
            allowed = True  # Proceed to downstream api handlers

        # 3. Handle Rate Limit Violations (Blocked Traffic)
        if not allowed:
            latency = (time.perf_counter() - start_time) * 1000
            reset_in_seconds = max(0, int(reset_time - timestamp))

            # Expose HTTP 429 response structure
            error_detail = RateLimitErrorDetail(
                message="Rate limit exceeded. Please try again later.",
                limit=limit,
                burst_limit=burst_limit,
                current_count=current_count,
                reset_in_seconds=reset_in_seconds,
            )
            error_response = RateLimitErrorResponse(detail=error_detail)

            # Log blocked request
            logger.warning(
                f"Request Rate Limited - Client: {client_ip} on {method} {endpoint}",
                extra={
                    "request_id": request_id,
                    "client_ip": client_ip,
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": 429,
                    "latency_ms": round(latency, 2),
                    "allowed": False,
                },
            )

            # Update Prometheus Stats
            HTTP_REQUESTS_TOTAL.labels(
                method=method, endpoint=endpoint, status_code="429", allowed="false"
            ).inc()
            HTTP_REQUESTS_BLOCKED_TOTAL.labels(
                method=method, endpoint=endpoint, reason="rate_limit_exceeded"
            ).inc()

            # Return 429 response with RFC standard header 'Retry-After'
            return JSONResponse(
                status_code=429,
                content=error_response.model_dump(),
                headers={
                    "Retry-After": str(reset_in_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(reset_time)),
                    "X-Request-ID": request_id,
                },
            )

        # 4. Handle Allowed Traffic
        response = await call_next(request)
        
        # Calculate Latency in MS
        latency = (time.perf_counter() - start_time) * 1000
        status_code = response.status_code

        # Add rate limit headers to client response
        remaining_budget = max(0, limit - current_count)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining_budget)
        response.headers["X-RateLimit-Reset"] = str(int(reset_time))
        response.headers["X-Request-ID"] = request_id

        # Log request summary
        logger.info(
            f"HTTP Request Completed - {method} {endpoint} -> {status_code}",
            extra={
                "request_id": request_id,
                "client_ip": client_ip,
                "method": method,
                "endpoint": endpoint,
                "status_code": status_code,
                "latency_ms": round(latency, 2),
                "allowed": True,
            },
        )

        # Update telemetry
        HTTP_REQUESTS_TOTAL.labels(
            method=method, endpoint=endpoint, status_code=str(status_code), allowed="true"
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, endpoint=endpoint).observe(latency / 1000.0)

        return response

    def _extract_client_ip(self, request: Request) -> str:
        """Parses reverse proxy headers to retrieve the true client IP."""
        # 1. Check X-Forwarded-For header chain
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            # First element represents the originating client IP address
            return x_forwarded_for.split(",")[0].strip()

        # 2. Check X-Real-IP header
        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip:
            return x_real_ip.strip()

        # 3. Fallback to default client host
        if request.client:
            return request.client.host
        
        return "127.0.0.1"
