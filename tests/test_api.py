import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_api_status_success(async_client: AsyncClient) -> None:
    """Tests the /api/v1/status health check endpoint."""
    response = await async_client.get("/api/v1/status")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "environment" in data
    assert "redis_connected" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_api_data_pagination_validation(async_client: AsyncClient) -> None:
    """Tests pagination parameters and input validations on /api/v1/data."""
    # 1. Test normal pagination request
    response = await async_client.get("/api/v1/data?page=2&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["total"] == 20

    # 2. Test query parameter validation limit range (limit le 100)
    response_invalid_limit = await async_client.get("/api/v1/data?limit=200")
    assert response_invalid_limit.status_code == 422  # Validation Error

    # 3. Test query parameter validation page negative values (page ge 1)
    response_invalid_page = await async_client.get("/api/v1/data?page=0")
    assert response_invalid_page.status_code == 422  # Validation Error


@pytest.mark.asyncio
async def test_api_users_filtering(async_client: AsyncClient) -> None:
    """Tests the /api/v1/users endpoint with query filtering."""
    # 1. Fetch admins
    response_admin = await async_client.get("/api/v1/users?role=admin")
    assert response_admin.status_code == 200
    data = response_admin.json()
    assert data["count"] == 2
    for user in data["users"]:
        assert user["role"] == "admin"

    # 2. Fetch inactive users
    response_inactive = await async_client.get("/api/v1/users?is_active=false")
    assert response_inactive.status_code == 200
    data_inactive = response_inactive.json()
    assert data_inactive["count"] == 1
    assert data_inactive["users"][0]["username"] == "charlie_guest"


@pytest.mark.asyncio
async def test_api_orders_filtering(async_client: AsyncClient) -> None:
    """Tests the /api/v1/orders endpoint with query filtering."""
    # 1. Fetch orders by customer ID
    response_cust = await async_client.get("/api/v1/orders?customer_id=cust_88")
    assert response_cust.status_code == 200
    data = response_cust.json()
    assert data["count"] == 2
    assert data["orders"][0]["customer_id"] == "cust_88"

    # 2. Fetch orders by status
    response_status = await async_client.get("/api/v1/orders?status=pending")
    assert response_status.status_code == 200
    data_status = response_status.json()
    assert data_status["count"] == 1
    assert data_status["orders"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_analytics_summary_empty(async_client: AsyncClient) -> None:
    """With no traffic, the summary is zeroed but well-formed (zero-filled time series)."""
    response = await async_client.get("/api/v1/analytics/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 0
    assert data["blocked_requests"] == 0
    assert data["block_rate_pct"] == 0.0
    assert len(data["timeseries"]) > 0
    assert data["recent"] == []


@pytest.mark.asyncio
async def test_analytics_summary_reflects_blocked_traffic(async_client: AsyncClient) -> None:
    """Allowed and rate-limited requests are both aggregated correctly."""
    import asyncio

    for _ in range(12):  # /orders limit is 10 -> 2 blocked
        await async_client.get("/api/v1/orders")
    await asyncio.sleep(0.3)  # analytics are written by a background task

    data = (await async_client.get("/api/v1/analytics/summary")).json()
    assert data["total_requests"] == 12
    assert data["allowed_requests"] == 10
    assert data["blocked_requests"] == 2
    assert data["block_rate_pct"] == pytest.approx(16.67, abs=0.01)
    assert {s["status_code"]: s["count"] for s in data["status_codes"]} == {200: 10, 429: 2}
    assert data["top_abusive_clients"][0]["blocked"] == 2
    assert data["endpoints"][0]["endpoint"] == "/api/v1/orders"
    assert data["endpoints"][0]["blocked"] == 2
    assert len(data["recent"]) == 12
    assert sum(p["blocked"] for p in data["timeseries"]) == 2


@pytest.mark.asyncio
async def test_analytics_endpoint_is_not_rate_limited_or_logged(
    async_client: AsyncClient,
) -> None:
    """Dashboard polling must neither be blocked nor pollute the traffic stream."""
    import asyncio

    for _ in range(80):  # well above any per-route limit
        response = await async_client.get("/api/v1/analytics/summary")
        assert response.status_code == 200
        assert "X-RateLimit-Limit" not in response.headers
    await asyncio.sleep(0.2)
    assert (await async_client.get("/api/v1/analytics/summary")).json()["total_requests"] == 0


@pytest.mark.asyncio
async def test_analytics_summary_truncation_uses_covered_span(test_app, async_client: AsyncClient) -> None:
    """When the read cap is hit, the rate is computed over the covered span, not the full window."""
    import asyncio

    for _ in range(10):
        await async_client.get("/api/v1/orders")
    await asyncio.sleep(0.3)

    service = test_app.state.analytics_service
    full = await service.summarize(window_seconds=60)
    capped = await service.summarize(window_seconds=60, max_events=5)

    assert full.window_truncated is False
    assert full.effective_window_seconds == 60
    assert capped.window_truncated is True
    assert capped.total_requests == 5
    assert capped.effective_window_seconds < 60
    # 5 events over a ~1s span must read as a rate well above 5/60
    assert capped.requests_per_second > 5 / 60 * 5


@pytest.mark.asyncio
async def test_analytics_summary_includes_system_health_without_logging_status_calls(
    async_client: AsyncClient,
) -> None:
    """Dashboard health comes from the summary, so no /status traffic is generated or recorded."""
    import asyncio

    for _ in range(5):
        data = (await async_client.get("/api/v1/analytics/summary")).json()
    assert data["system"]["redis_connected"] is True
    assert data["system"]["environment"] == "test"
    assert data["system"]["version"]
    await asyncio.sleep(0.2)
    assert data["total_requests"] == 0
    assert (await async_client.get("/api/v1/analytics/summary")).json()["recent"] == []


@pytest.mark.asyncio
async def test_recent_blocked_lists_blocked_clients_independent_of_window(
    test_app, async_client: AsyncClient
) -> None:
    """Blocked requests (with client IP) stay listed even when the read cap hides them from the stream view."""
    import asyncio

    for _ in range(14):  # /orders limit is 10 -> 4 blocked
        await async_client.get("/api/v1/orders")
    for _ in range(40):  # newer, allowed traffic on another route
        await async_client.get("/api/v1/data")
    await asyncio.sleep(0.4)

    service = test_app.state.analytics_service
    capped = await service.summarize(window_seconds=60, max_events=10)  # sees only the newest 10 stream events
    assert all(r.allowed for r in capped.recent)  # the live-log view contains no blocked rows...
    assert len(capped.recent_blocked) == 4  # ...but the dedicated blocked feed still has all 4
    assert all(r.status_code == 429 and not r.allowed for r in capped.recent_blocked)
    assert capped.recent_blocked[0].client_ip  # IP is present
    assert capped.recent_blocked[0].timestamp >= capped.recent_blocked[-1].timestamp  # newest first
