from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_redis_repository
from app.core.config import settings
from app.repositories.redis_repository import RedisRepository

router = APIRouter()


class SystemStatusResponse(BaseModel):
    """Schema representing system health indicators."""

    status: str = Field(..., description="Overall system health status ('healthy' or 'degraded').")
    environment: str = Field(..., description="The configuration environment the server is running on.")
    redis_connected: bool = Field(..., description="Indicates whether Redis is reachable.")
    version: str = Field(..., description="The release version of the API service.")


@router.get(
    "/status",
    response_model=SystemStatusResponse,
    summary="Get Service Status",
    description="Check API and Redis backend connection health.",
)
async def get_status(
    redis_repo: RedisRepository = Depends(get_redis_repository),
) -> SystemStatusResponse:
    # Ping Redis to verify connectivity
    redis_healthy = await redis_repo.ping()
    
    # Resolve overall state
    system_state = "healthy" if redis_healthy else "degraded"

    return SystemStatusResponse(
        status=system_state,
        environment=settings.ENV,
        redis_connected=redis_healthy,
        version=settings.VERSION,
    )
