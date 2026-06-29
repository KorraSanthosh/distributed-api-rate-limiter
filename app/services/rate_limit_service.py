import logging
from typing import Dict

from app.core.config import settings
from app.models.domain import RateLimitPolicy, RateLimitResult
from app.repositories.redis_repository import RedisRepository

logger = logging.getLogger("app")


class RateLimitService:
    """Orchestrates rate limiting operations across API endpoints."""

    def __init__(self, redis_repository: RedisRepository) -> None:
        self.redis_repo = redis_repository

        # Define route-specific Rate Limit Policies (Route-level Granularity)
        self.policies: Dict[str, RateLimitPolicy] = {
            "/api/v1/status": RateLimitPolicy(window_seconds=60, max_requests=100, burst_limit=120),
            "/api/v1/users": RateLimitPolicy(window_seconds=60, max_requests=30, burst_limit=45),
            "/api/v1/orders": RateLimitPolicy(window_seconds=60, max_requests=10, burst_limit=15),
            "/api/v1/data": RateLimitPolicy(window_seconds=60, max_requests=60, burst_limit=80),
        }

        # Fallback default policy loaded from app configurations
        self.default_policy = RateLimitPolicy(
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            max_requests=settings.RATE_LIMIT_MAX_REQUESTS,
            burst_limit=settings.RATE_LIMIT_BURST_LIMIT,
        )
        logger.info("RateLimitService initialized with endpoint policies.")

    def _resolve_policy(self, endpoint: str) -> RateLimitPolicy:
        """Determines which rate limit policy governs the given endpoint."""
        # Simple prefix match to resolve policy. Handles dynamic paths like /api/v1/users/123
        for route, policy in self.policies.items():
            if endpoint.startswith(route):
                return policy
        return self.default_policy

    async def evaluate_request(
        self, client_ip: str, endpoint: str, method: str, timestamp: float
    ) -> RateLimitResult:
        """Evaluates whether a client's request is allowed or blocked.

        Args:
            client_ip: Identifies the requester (IP address)
            endpoint: Target path of the request
            method: HTTP method (GET, POST, etc.)
            timestamp: Seconds since epoch

        Returns:
            RateLimitResult domain object.
        """
        policy = self._resolve_policy(endpoint)
        key = f"rate_limit:{client_ip}"

        # Resolve burst limit (guaranteed fallback)
        burst = policy.burst_limit if policy.burst_limit is not None else int(policy.max_requests * 1.25)

        # Query atomic lua-rate limiter in Redis
        allowed, current_count, _ = await self.redis_repo.check_rate_limit(
            key=key,
            now=timestamp,
            window=policy.window_seconds,
            limit=policy.max_requests,
            burst_limit=burst,
        )

        # Determine reset time (when the client's current block completely clears)
        ttl_seconds = await self.redis_repo.get_ttl(key)
        reset_time = timestamp + (ttl_seconds if ttl_seconds > 0 else policy.window_seconds)

        return RateLimitResult(
            allowed=allowed,
            current_count=current_count,
            limit=policy.max_requests,
            burst_limit=burst,
            reset_time=reset_time,
            policy=policy,
        )
