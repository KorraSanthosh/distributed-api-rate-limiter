import ipaddress
import time
import uuid
import logging
from functools import lru_cache
from typing import Callable, Awaitable, Optional, Tuple, Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.metrics import (
    HTTP_REQUESTS_TOTAL,
    HTTP_REQUESTS_BLOCKED_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    APP_ERRORS_TOTAL,
)
from app.schemas.rate_limit import RateLimitErrorResponse, RateLimitErrorDetail
from app.services.rate_limit_service import RateLimitService

logger = logging.getLogger("app")

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


@lru_cache(maxsize=8)
def _parse_trusted_proxies(raw: str) -> Tuple[IPNetwork, ...]:
    """Parses a comma-separated list of IPs/CIDRs, skipping invalid entries."""
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            logger.warning(f"Ignoring invalid TRUSTED_PROXIES entry: {item!r}")
    return tuple(networks)


def _parse_ip(value: str) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(ip: str, networks: Tuple[IPNetwork, ...]) -> bool:
    addr = _parse_ip(ip)
    return addr is not None and any(addr in net for net in networks)


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
        bypass_paths = [
            "/metrics", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
            "/api/v1/analytics",  # dashboard polling: neither rate limited nor logged as traffic
        ]
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
        """Resolves the client IP, trusting proxy headers only from trusted proxies.

        Forwarded headers are client-controlled unless set by a proxy we trust, so
        they are ignored unless the socket peer is in TRUSTED_PROXIES. For
        X-Forwarded-For the chain is walked right-to-left and the first address that
        is not a trusted proxy is the client (anything left of it is spoofable).
        """
        peer = request.client.host if request.client else "127.0.0.1"
        networks = _parse_trusted_proxies(settings.TRUSTED_PROXIES)
        if not networks or not _is_trusted(peer, networks):
            return peer

        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if x_forwarded_for:
            for hop in reversed(x_forwarded_for.split(",")):
                hop = hop.strip()
                if _parse_ip(hop) is None:
                    return peer  # malformed chain: do not trust any of it
                if not _is_trusted(hop, networks):
                    return hop
            return peer

        x_real_ip = request.headers.get("X-Real-IP")
        if x_real_ip and _parse_ip(x_real_ip) is not None:
            return x_real_ip.strip()

        return peer
