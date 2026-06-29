from fastapi import Request

from app.repositories.redis_repository import RedisRepository
from app.services.analytics_service import AnalyticsService
from app.services.rate_limit_service import RateLimitService


def get_redis_repository(request: Request) -> RedisRepository:
    """Dependency provider for the Redis repository.

    Requires the repository to be initialized and attached to app.state on startup.
    """
    return request.app.state.redis_repo


def get_rate_limit_service(request: Request) -> RateLimitService:
    """Dependency provider for the Rate Limiting service."""
    return request.app.state.rate_limit_service


def get_analytics_service(request: Request) -> AnalyticsService:
    """Dependency provider for the Traffic Analytics service."""
    return request.app.state.analytics_service
