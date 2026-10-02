from fastapi import APIRouter, Depends, Query

from app.api.deps import get_analytics_service
from app.schemas.analytics import AnalyticsSummary
from app.services.analytics_service import AnalyticsService

router = APIRouter()


@router.get(
    "/analytics/summary",
    response_model=AnalyticsSummary,
    summary="Traffic Analytics Summary",
    description="Aggregated request statistics from the Redis traffic stream (used by the web dashboard).",
)
async def get_analytics_summary(
    window_seconds: int = Query(default=60, ge=5, le=900, description="KPI window in seconds."),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummary:
    return await service.summarize(window_seconds=window_seconds)
