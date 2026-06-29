from unittest.mock import AsyncMock, patch
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from redis.exceptions import ConnectionError

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
