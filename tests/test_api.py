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
