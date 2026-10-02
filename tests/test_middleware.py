import asyncio
from unittest.mock import patch
import pytest
import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from httpx import AsyncClient
from redis.exceptions import ConnectionError

from app.core.config import settings
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.repositories.redis_repository import RedisRepository


@pytest.mark.asyncio
async def test_middleware_injects_headers_and_succeeds(async_client: AsyncClient) -> None:
    """Verifies that normal requests receive proper tracing and rate-limiting headers."""
    # Hit an endpoint (e.g. status) with custom IP
    headers = {"X-Forwarded-For": "10.0.0.1"}
    response = await async_client.get("/api/v1/status", headers=headers)
    
    assert response.status_code == 200
    
    # Assert headers exist
    assert "X-Request-ID" in response.headers
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers
    
    assert int(response.headers["X-RateLimit-Remaining"]) >= 0


@pytest.mark.asyncio
async def test_middleware_blocks_and_returns_429(async_client: AsyncClient) -> None:
    """Verifies that exceeding the limits returns HTTP 429 with correct schema and headers."""
    headers = {"X-Forwarded-For": "10.0.0.2"}
    
    # Target endpoint: /api/v1/orders (Limit: 10 per 60s, Burst: 15 per 2s)
    # Fire 11 requests. The 11th should be blocked by the normal limit.
    responses = []
    for _ in range(11):
        resp = await async_client.get("/api/v1/orders", headers=headers)
        responses.append(resp)
        
    # Check that at least the last request is blocked with HTTP 429
    last_resp = responses[-1]
    assert last_resp.status_code == 429
    
    # Verify rate limit headers on 429 response
    assert last_resp.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in last_resp.headers
    
    # Verify body structure
    body = last_resp.json()
    assert "detail" in body
    assert "limit" in body["detail"]
    assert "burst_limit" in body["detail"]
    assert "current_count" in body["detail"]
    assert "reset_in_seconds" in body["detail"]
    assert body["detail"]["current_count"] >= body["detail"]["limit"]


@pytest.mark.asyncio
async def test_middleware_bypasses_static_endpoints(async_client: AsyncClient) -> None:
    """Verifies that metrics and docs endpoints bypass rate limiter checks."""
    # Hit metrics
    response = await async_client.get("/metrics")
    assert response.status_code == 200
    # Metrics should not have X-RateLimit headers
    assert "X-RateLimit-Limit" not in response.headers


@pytest.mark.asyncio
async def test_middleware_fails_open_on_redis_outage(
    test_app: FastAPI, async_client: AsyncClient
) -> None:
    """Verifies fail-open behavior: requests still succeed when Redis is down."""
    # Mock Redis check_rate_limit to raise a connection error
    redis_repo: RedisRepository = test_app.state.redis_repo
    
    with patch.object(
        redis_repo, "check_rate_limit", side_effect=ConnectionError("Redis connection lost")
    ):
        headers = {"X-Forwarded-For": "10.0.0.3"}
        response = await async_client.get("/api/v1/status", headers=headers)
        
        # Request should succeed despite database outage (fail-open)
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers


async def _wait_for_stream_entries(
    redis_client: "aioredis.Redis", minimum: int, timeout: float = 2.0
) -> list:
    """Polls the analytics stream until it holds `minimum` entries (logging is async)."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        entries = await redis_client.xrange("api_traffic_stream")
        if len(entries) >= minimum or asyncio.get_event_loop().time() > deadline:
            return entries
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_blocked_requests_are_logged_to_analytics_stream(
    async_client: AsyncClient, redis_test_client: "aioredis.Redis"
) -> None:
    """429 responses must reach the analytics stream (AnalyticsMiddleware wraps the limiter)."""
    # /api/v1/orders allows 10 per window: 12 requests -> 10 allowed, 2 blocked
    for _ in range(12):
        await async_client.get("/api/v1/orders")

    entries = await _wait_for_stream_entries(redis_test_client, minimum=12)
    assert len(entries) == 12
    blocked = [f for _, f in entries if f["status_code"] == "429"]
    allowed = [f for _, f in entries if f["status_code"] == "200"]
    assert len(blocked) == 2
    assert len(allowed) == 10
    assert all(f["allowed"] == "False" for f in blocked)


@pytest.mark.asyncio
async def test_rate_limits_are_independent_per_route(async_client: AsyncClient) -> None:
    """Traffic on one route must not consume another route's budget."""
    for _ in range(10):
        assert (await async_client.get("/api/v1/status")).status_code == 200

    # Same client, different route: its own counter is still empty
    first_orders = await async_client.get("/api/v1/orders")
    assert first_orders.status_code == 200
    assert first_orders.headers["X-RateLimit-Remaining"] == "9"

    # ...while the route's own limit is still enforced
    for _ in range(9):
        await async_client.get("/api/v1/orders")
    assert (await async_client.get("/api/v1/orders")).status_code == 429


@pytest.mark.asyncio
async def test_spoofed_forwarded_header_ignored_by_default(async_client: AsyncClient) -> None:
    """Without trusted proxies, rotating X-Forwarded-For must not evade the limit."""
    statuses = [
        (await async_client.get("/api/v1/orders", headers={"X-Forwarded-For": f"7.7.7.{i}"})).status_code
        for i in range(15)
    ]
    assert statuses.count(200) == 10
    assert statuses.count(429) == 5


@pytest.mark.asyncio
async def test_forwarded_header_honoured_from_trusted_proxy(
    async_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the peer is a trusted proxy, each forwarded client gets its own budget."""
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", "127.0.0.1")
    statuses = [
        (await async_client.get("/api/v1/orders", headers={"X-Forwarded-For": f"7.7.7.{i}"})).status_code
        for i in range(15)
    ]
    assert statuses == [200] * 15


def _request(peer: str, headers: dict) -> Request:
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (peer, 1234),
            "method": "GET",
            "path": "/",
        }
    )


@pytest.mark.parametrize(
    "trusted, peer, headers, expected",
    [
        ("", "1.2.3.4", {"X-Forwarded-For": "9.9.9.9"}, "1.2.3.4"),  # untrusted: ignore
        ("10.0.0.0/8", "5.5.5.5", {"X-Forwarded-For": "9.9.9.9"}, "5.5.5.5"),  # peer not a proxy
        ("10.0.0.0/8", "10.0.0.1", {"X-Forwarded-For": "9.9.9.9"}, "9.9.9.9"),
        # client-injected left entry is skipped; right-most untrusted hop wins
        ("10.0.0.0/8", "10.0.0.1", {"X-Forwarded-For": "6.6.6.6, 8.8.8.8, 10.0.0.2"}, "8.8.8.8"),
        ("10.0.0.0/8", "10.0.0.1", {"X-Forwarded-For": "not-an-ip"}, "10.0.0.1"),  # malformed
        ("10.0.0.0/8", "10.0.0.1", {"X-Real-IP": "9.9.9.9"}, "9.9.9.9"),
        ("10.0.0.0/8", "10.0.0.1", {"X-Real-IP": "garbage"}, "10.0.0.1"),
        ("10.0.0.0/8", "10.0.0.1", {}, "10.0.0.1"),
    ],
)
def test_extract_client_ip(
    monkeypatch: pytest.MonkeyPatch, trusted: str, peer: str, headers: dict, expected: str
) -> None:
    monkeypatch.setattr(settings, "TRUSTED_PROXIES", trusted)
    middleware = RateLimiterMiddleware(app=lambda *a: None)
    assert middleware._extract_client_ip(_request(peer, headers)) == expected
