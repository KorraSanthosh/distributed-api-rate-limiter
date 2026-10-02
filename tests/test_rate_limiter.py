import pytest
import time
from app.repositories.redis_repository import RedisRepository


@pytest.mark.asyncio
async def test_rate_limiter_allows_requests_within_limit() -> None:
    """Verifies that requests within the policy limits are allowed."""
    repo = RedisRepository()
    key = "test_limit:192.168.1.1"
    now = time.time()
    
    # Policy: 3 requests allowed in 5 seconds. Burst limit: 2 in 2 seconds.
    # Request 1
    allowed, count, burst = await repo.check_rate_limit(key, now, window=5, limit=3, burst_limit=2)
    assert allowed is True
    assert count == 1
    assert burst == 1

    # Request 2 (1 second later)
    allowed, count, burst = await repo.check_rate_limit(key, now + 1.0, window=5, limit=3, burst_limit=2)
    assert allowed is True
    assert count == 2
    assert burst == 2
    
    await repo.close()


@pytest.mark.asyncio
async def test_rate_limiter_blocks_above_limit() -> None:
    """Verifies that requests exceeding the maximum limit are blocked."""
    repo = RedisRepository()
    key = "test_limit:192.168.1.2"
    now = time.time()

    # Policy: 3 requests allowed in 10 seconds. Burst limit: 5.
    # Make 3 allowed requests
    for i in range(3):
        allowed, count, _ = await repo.check_rate_limit(key, now + i * 0.1, window=10, limit=3, burst_limit=5)
        assert allowed is True
        assert count == i + 1

    # 4th request must be blocked
    allowed, count, _ = await repo.check_rate_limit(key, now + 0.4, window=10, limit=3, burst_limit=5)
    assert allowed is False
    assert count == 3  # Count should not increment for blocked requests
    
    await repo.close()


@pytest.mark.asyncio
async def test_rate_limiter_burst_limits() -> None:
    """Verifies that requests exceeding the short burst window limits are blocked."""
    repo = RedisRepository()
    key = "test_limit:192.168.1.3"
    now = time.time()

    # Policy: 10 requests allowed in 60 seconds. Burst limit: 2 requests in 2 seconds.
    # Request 1 (T=0)
    allowed, count, burst = await repo.check_rate_limit(key, now, window=60, limit=10, burst_limit=2)
    assert allowed is True
    
    # Request 2 (T=0.5)
    allowed, count, burst = await repo.check_rate_limit(key, now + 0.5, window=60, limit=10, burst_limit=2)
    assert allowed is True
    assert burst == 2

    # Request 3 (T=1.0) -> Exceeds burst limit (2 requests in 2 seconds) even though main limit is 10
    allowed, count, burst = await repo.check_rate_limit(key, now + 1.0, window=60, limit=10, burst_limit=2)
    assert allowed is False
    assert count == 2  # Blocked, so total main count stays at 2
    
    # Request 4 (T=2.5) -> Outside 2-second burst window since T=0, T=0.5. 
    # Current burst window for T=2.5 checks [0.5, 2.5] which only has T=0.5 (count 1). Thus, this should be allowed.
    allowed, count, burst = await repo.check_rate_limit(key, now + 2.5, window=60, limit=10, burst_limit=2)
    assert allowed is True
    assert count == 3
    
    await repo.close()


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window_eviction() -> None:
    """Verifies that expired timestamps are evicted from the sorted set."""
    repo = RedisRepository()
    key = "test_limit:192.168.1.4"
    now = time.time()

    # Policy: 2 requests per 5 seconds. Burst limit: 5.
    # Request 1 (T=0)
    allowed, count, _ = await repo.check_rate_limit(key, now, window=5, limit=2, burst_limit=5)
    assert allowed is True

    # Request 2 (T=1)
    allowed, count, _ = await repo.check_rate_limit(key, now + 1.0, window=5, limit=2, burst_limit=5)
    assert allowed is True

    # Request 3 (T=4.9) -> Blocked (within 5 seconds window)
    allowed, count, _ = await repo.check_rate_limit(key, now + 4.9, window=5, limit=2, burst_limit=5)
    assert allowed is False

    # Request 4 (T=5.1) -> Allowed (T=0 has cleared, T=1 is still in window. Total elements in [0.1, 5.1] is 1: T=1)
    allowed, count, _ = await repo.check_rate_limit(key, now + 5.1, window=5, limit=2, burst_limit=5)
    assert allowed is True
    assert count == 2  # Current active request count is 2 (T=1.0 and T=5.1)
    
    await repo.close()


@pytest.mark.asyncio
async def test_pool_exhaustion_waits_instead_of_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    """With far more concurrent callers than connections, requests must queue, not raise
    'Too many connections' (which would make the limiter fail open exactly under load)."""
    import asyncio

    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_MAX_CONNECTIONS", 3)
    monkeypatch.setattr(settings, "REDIS_POOL_TIMEOUT", 5.0)
    repo = RedisRepository()
    now = time.time()
    try:
        results = await asyncio.gather(
            *[
                repo.check_rate_limit(f"test_pool:{i}", now, window=10, limit=5, burst_limit=5)
                for i in range(200)
            ]
        )
    finally:
        await repo.close()
    assert len(results) == 200
    assert all(allowed for allowed, _, _ in results)  # each key is used once -> all allowed
