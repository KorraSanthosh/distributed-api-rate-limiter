import os
from typing import AsyncGenerator
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

# Set environment variables for testing profile before imports
os.environ["ENV"] = "test"

from app.core.config import settings
from app.main import app as fastapi_app
from app.repositories.redis_repository import RedisRepository
from app.services.analytics_service import AnalyticsService
from app.services.rate_limit_service import RateLimitService


@pytest_asyncio.fixture
async def redis_test_client() -> AsyncGenerator[aioredis.Redis, None]:
    """Establishes an async connection to the test Redis DB."""
    # Ensure test settings is loaded (should use DB 9)
    assert settings.ENV == "test"
    assert settings.REDIS_DB == 9
    
    pool = aioredis.ConnectionPool(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
    )
    client = aioredis.Redis(connection_pool=pool)
    
    # Ping once to check connectivity
    try:
        await client.ping()
    except Exception as e:
        pytest.skip(f"Test Redis server is unavailable on port {settings.REDIS_PORT}: {e}")
        
    yield client
    await pool.disconnect()


@pytest_asyncio.fixture(autouse=True)
async def clean_redis(redis_test_client: aioredis.Redis) -> AsyncGenerator[None, None]:
    """Automatically flushes the Redis test database before each test runs."""
    await redis_test_client.flushdb()
    yield
    await redis_test_client.flushdb()


@pytest_asyncio.fixture
async def test_app() -> AsyncGenerator[FastAPI, None]:
    """Bootstraps the FastAPI application in test mode."""
    # Override repositories/services to use test context
    redis_repo = RedisRepository()
    
    fastapi_app.state.redis_repo = redis_repo
    fastapi_app.state.rate_limit_service = RateLimitService(redis_repo)
    fastapi_app.state.analytics_service = AnalyticsService(redis_repo)
    
    yield fastapi_app
    
    await redis_repo.close()


@pytest_asyncio.fixture
async def async_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Yields an HTTPX AsyncClient for making requests to the FastAPI application."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
